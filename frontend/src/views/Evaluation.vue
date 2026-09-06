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

        <el-switch
          v-model="evaluationStore.includeLlmJudge"
          active-text="启用 LLM Judge 裁判打分 (10% 权重)"
          inline-prompt
        />
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
            <el-table-column label="规则得分 (60%)" width="120" align="center">
              <template #default="{ row }">
                <span class="score-badge rule">{{ formatScore(row.ruleScore) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="用户反馈 (30%)" width="120" align="center">
              <template #default="{ row }">
                <span class="score-badge feed">{{ formatScore(row.userFeedbackScore) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="LLM 裁判 (10%)" width="120" align="center">
              <template #default="{ row }">
                <span class="score-badge llm">{{ formatScore(row.llmJudgeScore) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="综合分" width="100" align="center">
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
  gap: 4px;
}

.range-chip {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 3px 10px;
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
