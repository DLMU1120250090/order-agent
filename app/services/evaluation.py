import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.agents.evaluation import EvaluationJudgeAgent
from app.models.database import FeedbackRow, RequestTraceRow
from app.models.schemas import EvaluationReport, EvaluationRequest, TraceEvaluationResult

log = logging.getLogger("travel.evaluation")

# 6 维出行槽位键名集合
SLOT_NAMES = {"destination", "tripDate", "budget", "travelStyle", "transportMode", "companion"}
# 资金/绝对化敏感词（合规项扣分）
FORBIDDEN_PHRASES = ["代付", "自动付款", "替我付款", "保证", "包退"]


class EvaluationService:
    """
    质量评估分析服务（步骤 13）。
    规则 60% + LLM Judge 10% + 用户反馈 30%；缺失项权重归一。
    在原有意图/槽位/澄清/成本/时延/降级/合规/幻觉/多轮指标基础上，
    扩展出行域指标：planFeasibility / bookingSuccessRate / userConfirmRate /
    changeDecisionOptimality / orderModifySuccessRate / savingsAchieved / priceWatchHitRate 等。
    """

    def __init__(self, judge_agent: EvaluationJudgeAgent):
        self.judge_agent = judge_agent

    async def evaluate(self, db: AsyncSession, user_id: int, request: EvaluationRequest) -> EvaluationReport:
        if not request or not request.startAt or not request.endAt or request.startAt >= request.endAt:
            raise HTTPException(status_code=400, detail="评估时间范围不合法")
        limit = request.limit or 1000

        trace_query = (
            select(RequestTraceRow)
            .where(
                RequestTraceRow.user_id == user_id,
                RequestTraceRow.created_at >= request.startAt,
                RequestTraceRow.created_at < request.endAt,
            )
            .order_by(RequestTraceRow.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(trace_query)
        traces = list(result.scalars().all())

        if not traces:
            return EvaluationReport(
                startAt=request.startAt,
                endAt=request.endAt,
                totalTraces=0,
                labeledTraces=0,
                avgScore=None,
                metricAverages={},
                traceResults=[],
            )

        session_ids = list({t.session_id for t in traces if t.session_id})
        feedbacks_dict: Dict[str, List[FeedbackRow]] = {}
        if session_ids:
            fb_res = await db.execute(
                select(FeedbackRow).where(
                    FeedbackRow.user_id == user_id,
                    FeedbackRow.session_id.in_(session_ids),
                    FeedbackRow.created_at >= request.startAt,
                    FeedbackRow.created_at < request.endAt,
                )
            )
            for fb in fb_res.scalars().all():
                feedbacks_dict.setdefault(fb.session_id, []).append(fb)

        trace_results = []
        for t in traces:
            res = await self._evaluate_single_trace(t, feedbacks_dict.get(t.session_id, []), request.includeLlmJudge)
            trace_results.append(res)

        total_traces = len(traces)
        labeled_traces = sum(1 for t in traces if t.expected_intent or t.expected_slots or t.expected_clarify_action)
        avg_score = self._average([tr.score for tr in trace_results])

        metrics_lists: Dict[str, List[float]] = {}
        for tr in trace_results:
            for name, val in tr.metrics.items():
                if val is not None:
                    metrics_lists.setdefault(name, []).append(val)
        metric_averages = {name: self._average(vals) for name, vals in metrics_lists.items()}

        return EvaluationReport(
            startAt=request.startAt,
            endAt=request.endAt,
            totalTraces=total_traces,
            labeledTraces=labeled_traces,
            avgScore=avg_score,
            metricAverages=metric_averages,
            traceResults=trace_results,
        )

    async def _evaluate_single_trace(
        self,
        row: RequestTraceRow,
        feedbacks: List[FeedbackRow],
        include_judge: bool,
    ) -> TraceEvaluationResult:
        snapshot = self._parse_trace_json(row)
        metrics: Dict[str, Optional[float]] = {}

        metrics["intentAccuracy"] = self._intent_accuracy(row.expected_intent, snapshot.get("intent"))
        metrics["slotAccuracy"] = self._slot_accuracy(row.expected_slots, snapshot.get("slots"))
        metrics["clarifyNecessityAccuracy"] = self._clarify_accuracy(row.expected_clarify_action, snapshot.get("clarifyAction"))

        token_cost = snapshot.get("tokenCost")
        metrics["tokenCost"] = float(token_cost) if token_cost is not None else None
        metrics["tokenCostScore"] = self._cost_score(token_cost)

        duration = row.duration_ms
        metrics["latencyMs"] = float(duration) if duration is not None else None
        metrics["latencyScore"] = self._latency_score(duration)

        metrics["fallbackRate"] = 1.0 if snapshot.get("fallbackUsed") else 0.0
        metrics["fallbackScore"] = 0.0 if snapshot.get("fallbackUsed") else 1.0
        metrics["safetyCompliance"] = 1.0 if snapshot.get("safetyCompliance") else 0.0
        metrics["hallucinationControl"] = 1.0 if snapshot.get("hallucinationFree") else 0.0
        metrics["multiTurnConsistency"] = snapshot.get("multiTurnConsistency")

        # ---- 出行域扩展指标（步骤 13） ----
        metrics["planFeasibility"] = 1.0 if snapshot.get("planRanked") else None
        metrics["bookingSuccessRate"] = self._booking_success(snapshot)
        metrics["userConfirmRate"] = self._user_confirm(snapshot)
        metrics["changeDecisionOptimality"] = self._change_optimality(snapshot)
        metrics["orderModifySuccessRate"] = self._order_modify_success(snapshot)
        metrics["savingsAchieved"] = self._savings_achieved(snapshot)
        metrics["priceWatchHitRate"] = self._price_watch_hit(snapshot)

        judge_result = None
        if include_judge:
            judge_input = {
                "predictedIntent": snapshot.get("intent"),
                "predictedSlots": snapshot.get("slots"),
                "predictedClarifyAction": snapshot.get("clarifyAction"),
                "finalReply": snapshot.get("finalText"),
                "planCount": snapshot.get("recommendationCount"),
                "safetyComplianceByRule": snapshot.get("safetyCompliance"),
                "hallucinationFreeByRule": snapshot.get("hallucinationFree"),
            }
            try:
                judge_res = await self.judge_agent.call(row.trace_id, json.dumps(judge_input, ensure_ascii=False))
                judge_result = {
                    "explanationQuality": self._clamp_score(judge_res.explanationQuality),
                    "naturalness": self._clamp_score(judge_res.naturalness),
                    "reason": judge_res.reason,
                }
                metrics["explanationQuality"] = judge_result["explanationQuality"]
                metrics["naturalness"] = judge_result["naturalness"]
            except Exception as e:  # noqa: BLE001
                log.warning("大模型裁判调用失败 trace_id=%s: %s", row.trace_id, e)

        fb_score = self._feedback_score(feedbacks)
        rule_metrics = [
            metrics["intentAccuracy"],
            metrics["slotAccuracy"],
            metrics["clarifyNecessityAccuracy"],
            metrics["tokenCostScore"],
            metrics["latencyScore"],
            metrics["fallbackScore"],
            metrics["safetyCompliance"],
            metrics["hallucinationControl"],
            metrics["multiTurnConsistency"],
            metrics["planFeasibility"],
            metrics["bookingSuccessRate"],
            metrics["userConfirmRate"],
            metrics["changeDecisionOptimality"],
            metrics["orderModifySuccessRate"],
        ]
        rule_score = self._average(rule_metrics)

        llm_judge_score = None
        if judge_result:
            llm_judge_score = self._average([
                judge_result["explanationQuality"] / 5.0,
                judge_result["naturalness"] / 5.0,
            ])

        total_score = self._weighted_score(rule_score, llm_judge_score, fb_score)
        detail = {
            "predictedIntent": snapshot.get("intent"),
            "predictedSlots": snapshot.get("slots"),
            "predictedClarifyAction": snapshot.get("clarifyAction"),
            "expectedIntent": row.expected_intent,
            "expectedSlots": self._parse_json_safe(row.expected_slots),
            "expectedClarifyAction": row.expected_clarify_action,
            "feedbackCount": len(feedbacks),
            "judgeMode": "LLM_AS_JUDGE" if include_judge else "DISABLED",
            "judgeReason": judge_result["reason"] if judge_result else None,
        }

        return TraceEvaluationResult(
            traceId=row.trace_id,
            sessionId=row.session_id,
            createdAt=row.created_at,
            score=self._to_percent(total_score),
            ruleScore=self._to_percent(rule_score),
            llmJudgeScore=self._to_percent(llm_judge_score),
            userFeedbackScore=self._to_percent(fb_score),
            metrics=metrics,
            detail=detail,
        )

    def _parse_trace_json(self, row: RequestTraceRow) -> dict:
        events = []
        if isinstance(row.trace_json, dict):
            events = row.trace_json.get("events") or []
        elif isinstance(row.trace_json, str):
            try:
                events = json.loads(row.trace_json).get("events") or []
            except Exception:
                events = []

        intent = None
        clarify_action = None
        token_cost = 0
        has_token = False
        fallback_used = row.status == "FAILED"
        ranked_ids = set()
        response_ids = set()
        excluded_ids = []
        final_text = ""
        slots = {}
        plan_ranked = False
        booking_started = False
        payment_confirmed = False
        payment_detected = False
        change_decision = None
        order_modified = False
        price_drop = False

        for e in events:
            ev_type = e.get("eventType")
            if not ev_type:
                continue
            if e.get("errorMessage") or ev_type == "REQUEST_FAILED":
                fallback_used = True
            if ev_type == "AGENT_CALL" and e.get("totalTokens") is not None:
                token_cost += int(e.get("totalTokens"))
                has_token = True

            out_str = e.get("outputPayload")
            output = {}
            if out_str:
                try:
                    output = json.loads(out_str)
                except Exception:
                    pass

            if ev_type == "INTENT_REVISED":
                intent = output.get("intent") or intent
                if "slots" in output:
                    slots = output.get("slots") or {}
            elif ev_type == "SLOTS_MERGED":
                slots = output or {}
            elif ev_type == "CLARIFY_DECISION":
                clarify_action = output.get("action") or clarify_action
            elif ev_type == "PLAN_RANKED":
                plan_ranked = True
                ranked = output.get("options") or []
                ranked_ids.update(str(r) for r in ranked if r)
            elif ev_type == "RESPONSE_READY":
                final_text = output.get("speechText") or final_text
                blocks = output.get("displayBlocks") or []
                for b in blocks:
                    if isinstance(b, dict) and b.get("planId"):
                        response_ids.add(str(b.get("planId")))
            elif ev_type == "BOOKING_STARTED":
                booking_started = True
            elif ev_type == "PAYMENT_DETECTED":
                payment_detected = True
            elif ev_type == "PAYMENT_CONFIRMED":
                payment_confirmed = True
            elif ev_type == "ORDER_CHANGE_DECISION":
                change_decision = output
            elif ev_type == "PRICE_WATCH_SCANNED" or ev_type == "PRICE_DROP_DETECTED":
                price_drop = True
            elif ev_type in ("ORDER_CHANGED", "ORDER_REFUNDED"):
                order_modified = True
            elif ev_type == "ADJUST_CONTEXT_RESOLVED":
                excluded_ids = output.get("excludePlanIds") or []

        hallucination_free = not response_ids or response_ids.issubset(ranked_ids)
        safety_compliance = all(kw not in final_text for kw in FORBIDDEN_PHRASES)
        multi_turn_consistency = None
        if intent == "PLAN_ADJUST":
            multi_turn_consistency = 0.0 if not excluded_ids else (1.0 if not (response_ids & set(excluded_ids)) else 0.0)

        return {
            "intent": intent,
            "slots": slots,
            "clarifyAction": clarify_action,
            "tokenCost": token_cost if has_token else None,
            "fallbackUsed": fallback_used,
            "safetyCompliance": safety_compliance,
            "hallucinationFree": hallucination_free,
            "multiTurnConsistency": multi_turn_consistency,
            "finalText": final_text,
            "recommendationCount": len(response_ids),
            "planRanked": plan_ranked,
            "bookingStarted": booking_started,
            "paymentDetected": payment_detected,
            "paymentConfirmed": payment_confirmed,
            "changeDecision": change_decision,
            "orderModified": order_modified,
            "priceDrop": price_drop,
        }

    def _booking_success(self, snapshot: dict) -> Optional[float]:
        if snapshot.get("bookingStarted"):
            return 1.0 if snapshot.get("paymentConfirmed") else 0.0
        return None

    def _user_confirm(self, snapshot: dict) -> Optional[float]:
        if snapshot.get("bookingStarted"):
            return 1.0 if snapshot.get("paymentConfirmed") else 0.0
        return None

    def _change_optimality(self, snapshot: dict) -> Optional[float]:
        decision = snapshot.get("changeDecision")
        if not decision:
            return None
        rec = decision.get("recommended") or {}
        total_loss = rec.get("total_loss")
        if total_loss is None:
            return None
        return 1.0 if total_loss <= 0 else max(0.0, 1.0 - min(1.0, total_loss / 500.0))

    def _order_modify_success(self, snapshot: dict) -> Optional[float]:
        if not snapshot.get("changeDecision") and not snapshot.get("bookingStarted"):
            return None
        if snapshot.get("orderModified"):
            return 1.0
        return 0.0 if snapshot.get("changeDecision") else None

    def _savings_achieved(self, snapshot: dict) -> Optional[float]:
        decision = snapshot.get("changeDecision")
        if not decision:
            return None
        rec = decision.get("recommended") or {}
        loss = rec.get("total_loss")
        if loss is None:
            return None
        return max(0.0, min(1.0, (-loss) / 1000.0))

    def _price_watch_hit(self, snapshot: dict) -> Optional[float]:
        if not snapshot.get("priceDrop"):
            return None
        return 1.0

    def _intent_accuracy(self, expected: Optional[str], actual: Optional[str]) -> Optional[float]:
        if not expected or not expected.strip():
            return None
        return 1.0 if expected == actual else 0.0

    def _slot_accuracy(self, expected_json: Optional[str], actual_slots: dict) -> Optional[float]:
        if not expected_json or not expected_json.strip():
            return None
        try:
            expected = json.loads(expected_json)
        except Exception:
            return None
        compared, matched = 0, 0
        for name in SLOT_NAMES:
            exp_vals = expected.get(name) or []
            if not exp_vals:
                continue
            compared += 1
            act_vals = actual_slots.get(name) or []
            if set(exp_vals) == set(act_vals):
                matched += 1
        return matched / compared if compared > 0 else None

    def _clarify_accuracy(self, expected: Optional[str], actual: Optional[str]) -> Optional[float]:
        if not expected or not expected.strip():
            return None
        return 1.0 if expected == actual else 0.0

    def _cost_score(self, cost: Optional[int]) -> Optional[float]:
        if cost is None:
            return None
        if cost <= 1000:
            return 1.0
        if cost >= 3000:
            return 0.0
        return (3000.0 - cost) / 2000.0

    def _latency_score(self, latency: Optional[int]) -> Optional[float]:
        if latency is None:
            return None
        if latency <= 3000:
            return 1.0
        if latency >= 8000:
            return 0.0
        return (8000.0 - latency) / 5000.0

    def _feedback_score(self, feedbacks: List[FeedbackRow]) -> Optional[float]:
        scores = []
        for fb in feedbacks:
            if fb.rating is not None:
                scores.append(max(0, min(5, fb.rating)) / 5.0)
            elif fb.action:
                action = fb.action.upper()
                if action in ["LIKE", "UP", "ADOPT", "ACCEPT"]:
                    scores.append(1.0)
                elif action in ["DISLIKE", "DOWN", "REJECT"]:
                    scores.append(0.0)
                elif action in ["SWITCH", "CHANGE", "REFRESH"]:
                    scores.append(0.4)
        return self._average(scores)

    def _weighted_score(self, rule_score, judge_score, fb_score) -> Optional[float]:
        weighted, weight = 0.0, 0.0
        if rule_score is not None:
            weighted += rule_score * 0.6
            weight += 0.6
        if judge_score is not None:
            weighted += judge_score * 0.1
            weight += 0.1
        if fb_score is not None:
            weighted += fb_score * 0.3
            weight += 0.3
        return weighted / weight if weight > 0 else None

    def _average(self, values: List[Optional[float]]) -> Optional[float]:
        present = [v for v in values if v is not None]
        if not present:
            return None
        return sum(present) / len(present)

    def _to_percent(self, val: Optional[float]) -> Optional[float]:
        return round(val * 100.0, 2) if val is not None else None

    def _clamp_score(self, val: float) -> float:
        return max(1.0, min(5.0, val))

    def _parse_json_safe(self, text: Optional[str]) -> dict:
        if not text or not text.strip():
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}
