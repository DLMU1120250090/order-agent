<template>
  <div class="eval-workspace">
    <!-- Topbar -->
    <header class="eval-topbar">
      <div class="topbar-left">
        <div class="page-title">
          <el-icon><TrendCharts /></el-icon>
          <span>质量评测与持续优化闭环 (Evaluation Dashboard)</span>
        </div>

        <div class="range-chips">
          <button
            v-for="r in RANGES"
            :key="r.key"
            type="button"
            class="range-chip"
            :class="{ active: evaluationStore.selectedRange === r.key }"
            @click="handleRangeChange(r.key)"
          >
            {{ r.label }}
          </button>
        </div>

        <div class="judge-switch-box">
          <el-tooltip
            placement="bottom"
            effect="dark"
            :show-after="100"
          >
            <template #content>
              <div class="judge-tooltip-body">
                <div class="tip-title">🤖 LLM 裁判打分模式说明</div>
                <div class="tip-item">
                  <span class="tip-tag on">开启</span>
                  <span>调用大模型裁判对历史会话进行深度语义与意图质检，打分计入 <b>10%</b> 综合权重（耗时与 Token 开销略有增加）。</span>
                </div>
                <div class="tip-item">
                  <span class="tip-tag off">关闭 (默认)</span>
                  <span>关闭大模型以节省开销，综合评分公式自动重归一化为 <b>66.7% 规则合规 + 33.3% 用户反馈</b>。</span>
                </div>
              </div>
            </template>
            <div class="judge-label-wrap">
              <span class="judge-text">LLM 裁判打分</span>
              <el-icon class="judge-icon"><QuestionFilled /></el-icon>
            </div>
          </el-tooltip>
          <el-switch
            v-model="evaluationStore.includeLlmJudge"
            :disabled="evaluationStore.isLoading"
            active-text="开"
            inactive-text="关"
            inline-prompt
            size="small"
            class="judge-switch"
            @change="handleJudgeChange"
          />
        </div>
      </div>

      <div class="topbar-right">
        <el-button
          type="primary"
          :loading="evaluationStore.isLoading"
          @click="evaluationStore.runEvaluation"
        >
          <el-icon><VideoPlay /></el-icon>
          运行全量离线评估
        </el-button>
      </div>
    </header>

    <!-- Main Content Container with Loading -->
    <main v-loading="evaluationStore.isLoading" class="eval-main-pane">
      <div class="eval-content-flow">
        <!-- Section 1: Score Gauge & 60-30-10 Breakdown -->
        <ScoreGauge
          :overall-score="evaluationStore.overallScore"
          :breakdown="evaluationStore.scoreBreakdown"
        />

        <!-- Section 2: 4 Multi-Dimensional Quality Categories -->
        <MetricsRadar :metrics="evaluationStore.categorizedMetrics" />

        <!-- Section 3: 9 Failure Taxonomies Distribution -->
        <FailureDistribution :items="evaluationStore.failureTaxonomy" />

        <!-- Section 4: Sample Evaluated Traces Table -->
        <div v-if="evaluationStore.report?.traceResults?.length" class="sample-traces-card">
          <div class="table-header">
            <div class="table-title">
              <el-icon><Tickets /></el-icon>
              <span>评估样本明细 (Evaluated Traces Sample)</span>
            </div>
            <span class="table-count">共 {{ evaluationStore.report.traceResults.length }} 条样本</span>
          </div>

          <el-table
            :data="evaluationStore.report.traceResults.slice(0, 10)"
            stripe
            size="small"
            class="traces-table"
          >
            <el-table-column prop="traceId" label="Trace ID" min-width="160">
              <template #default="{ row }">
                <span class="code-txt">{{ row.traceId }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="sessionId" label="会话 ID" min-width="140">
              <template #default="{ row }">
                <span class="code-txt">{{ row.sessionId }}</span>
              </template>
            </el-table-column>
            <el-table-column label="规则得分 (60%)" width="115" align="center">
              <template #default="{ row }">
                <span class="score-badge rule">{{ formatScore(row.ruleScore) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="用户反馈 (30%)" width="125" align="center">
              <template #default="{ row }">
                <span v-if="row.userFeedbackScore != null" class="score-badge feed" :title="`显式评分: ${row.metrics?.explicitFeedbackScore ?? '无'} / 隐式采纳: ${row.metrics?.implicitAdoptionScore ?? '无'}`">
                  {{ formatScore(row.userFeedbackScore) }}
                </span>
                <span v-else class="score-badge disabled">无反馈</span>
              </template>
            </el-table-column>
            <el-table-column label="LLM 裁判 (10%)" width="120" align="center">
              <template #default="{ row }">
                <span v-if="row.llmJudgeScore != null" class="score-badge llm">{{ formatScore(row.llmJudgeScore) }}</span>
                <span v-else class="score-badge disabled">未启用</span>
              </template>
            </el-table-column>
            <el-table-column label="性能 (耗时/Token)" width="135" align="center">
              <template #default="{ row }">
                <span class="stat-meta">{{ row.metrics?.latencyMs != null ? `${row.metrics.latencyMs}ms` : '-' }}</span>
                <span v-if="row.metrics?.tokenCost" class="stat-tokens"> / {{ row.metrics.tokenCost }}tok</span>
              </template>
            </el-table-column>
            <el-table-column label="综合分" width="95" align="center">
              <template #default="{ row }">
                <strong>{{ formatScore(row.score) }}</strong>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" align="center">
              <template #default="{ row }">
                <router-link :to="{ path: '/admin/traces', query: { traceId: row.traceId } }" class="inspect-btn">
                  查看链路 →
                </router-link>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useEvaluationStore } from '@/stores/evaluation'
import ScoreGauge from '@/components/evaluation/ScoreGauge.vue'
import MetricsRadar from '@/components/evaluation/MetricsRadar.vue'
import FailureDistribution from '@/components/evaluation/FailureDistribution.vue'

const evaluationStore = useEvaluationStore()

const RANGES: { key: '1h' | 'today' | '7d' | '30d'; label: string }[] = [
  { key: '1h', label: '最近 1 小时' },
  { key: 'today', label: '今天' },
  { key: '7d', label: '最近 7 天' },
  { key: '30d', label: '最近 30 天' },
]

onMounted(async () => {
  await evaluationStore.runEvaluation()
})

function handleRangeChange(r: '1h' | 'today' | '7d' | '30d') {
  evaluationStore.selectedRange = r
  evaluationStore.runEvaluation()
}

function handleJudgeChange() {
  evaluationStore.runEvaluation()
}

function formatScore(score?: number): string {
  if (score == null) return '-'
  return score <= 1 ? `${Math.round(score * 100)}` : `${Math.round(score)}`
}
</script>

<style scoped>
.eval-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: #f8fafc;
  overflow: hidden;
}

.eval-topbar {
  height: 52px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 18px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.range-chips {
  display: flex;
  align-items: center;
  gap: 4px;
}

.range-chip {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 0 10px;
  height: 26px;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 11.5px;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s ease;
}

.range-chip:hover {
  background: #e2e8f0;
}

.range-chip.active {
  background: #2563eb;
  color: #ffffff;
  border-color: #2563eb;
  font-weight: 600;
}

.judge-switch-box {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #f1f5f9;
  padding: 0 8px;
  height: 26px;
  box-sizing: border-box;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  transition: all 0.15s ease;
}

.judge-switch-box:hover {
  border-color: #cbd5e1;
}

.judge-label-wrap {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  cursor: pointer;
  user-select: none;
}

.judge-text {
  font-size: 11.5px;
  font-weight: 600;
  color: #334155;
  line-height: 1;
}

.judge-icon {
  font-size: 12px;
  color: #64748b;
  transition: color 0.15s ease;
}

.judge-label-wrap:hover .judge-icon {
  color: #2563eb;
}

.judge-switch {
  --el-switch-on-color: #2563eb;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.eval-main-pane {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

.eval-content-flow {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.sample-traces-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.table-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 700;
  color: #0f172a;
}

.table-count {
  font-size: 11.5px;
  color: #94a3b8;
}

.traces-table {
  width: 100%;
}

.code-txt {
  font-family: monospace;
  font-size: 11.5px;
  color: #334155;
}

.score-badge {
  font-family: monospace;
  font-size: 11.5px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
}

.score-badge.rule { background: #eff6ff; color: #1d4ed8; }
.score-badge.feed { background: #ecfdf5; color: #059669; }
.score-badge.llm { background: #f5f3ff; color: #7c3aed; }
.score-badge.disabled { background: #f1f5f9; color: #94a3b8; font-weight: 500; }

.stat-meta {
  font-family: monospace;
  font-size: 11.5px;
  color: #334155;
  font-weight: 600;
}

.stat-tokens {
  font-family: monospace;
  font-size: 11px;
  color: #64748b;
}

.inspect-btn {
  font-size: 11.5px;
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
}

.inspect-btn:hover {
  text-decoration: underline;
}
</style>

<style>
.judge-tooltip-body {
  max-width: 290px;
  font-size: 12px;
  line-height: 1.55;
  color: #f8fafc;
  padding: 3px 1px;
}

.judge-tooltip-body .tip-title {
  font-weight: 700;
  margin-bottom: 6px;
  color: #93c5fd;
  font-size: 12.5px;
}

.judge-tooltip-body .tip-item {
  margin-bottom: 6px;
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.judge-tooltip-body .tip-item:last-child {
  margin-bottom: 0;
}

.judge-tooltip-body .tip-tag {
  display: inline-block;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: bold;
  flex-shrink: 0;
}

.judge-tooltip-body .tip-tag.on {
  background: rgba(34, 197, 94, 0.25);
  color: #4ade80;
}

.judge-tooltip-body .tip-tag.off {
  background: rgba(148, 163, 184, 0.25);
  color: #cbd5e1;
}
</style>
