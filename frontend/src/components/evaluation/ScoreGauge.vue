<template>
  <div class="gauge-card">
    <div class="card-header">
      <div class="title-group">
        <el-icon><DataAnalysis /></el-icon>
        <span class="header-title">系统综合质量评估分 (Overall Health Score)</span>
      </div>
      <span class="level-badge" :class="scoreLevelClass">{{ scoreLevelText }}</span>
    </div>

    <div class="gauge-body">
      <!-- Big Radial Score Circle -->
      <div class="radial-box">
        <svg class="radial-svg" viewBox="0 0 120 120">
          <circle
            cx="60"
            cy="60"
            r="50"
            class="bg-circle"
          />
          <circle
            cx="60"
            cy="60"
            r="50"
            class="progress-circle"
            :stroke-dasharray="circumference"
            :stroke-dashoffset="strokeDashoffset"
          />
        </svg>
        <div class="score-center">
          <span class="score-number">{{ overallScore }}</span>
          <span class="score-unit">/ 100 分</span>
        </div>
      </div>

      <!-- 3-Part Weight Breakdown -->
      <div class="breakdown-list">
        <div class="formula-banner">
          <span class="formula-label">评分公式权重:</span>
          <code v-if="breakdown.llmJudge !== null">综合分 = 60% × 规则得分 + 30% × 用户反馈 + 10% × LLM 裁判</code>
          <code v-else>综合分 = 66.7% × 规则得分 + 33.3% × 用户反馈 (LLM 裁判未启用)</code>
        </div>

        <div class="breakdown-item">
          <div class="item-header">
            <span class="item-name">
              <span class="weight-tag">{{ breakdown.llmJudge !== null ? '60% 权重' : '66.7% 权重' }}</span>
              <strong>规则层客观得分 (Rule Score)</strong>
            </span>
            <span class="item-score">{{ breakdown.rule }} 分</span>
          </div>
          <el-progress
            :percentage="breakdown.rule"
            :stroke-width="8"
            color="#3b82f6"
            :show-text="false"
          />
          <span class="item-hint">意图匹配、日期合规、槽位必填与确定性逻辑校验</span>
        </div>

        <div class="breakdown-item">
          <div class="item-header">
            <span class="item-name">
              <span class="weight-tag feed-tag">{{ breakdown.llmJudge !== null ? '30% 权重' : '33.3% 权重' }}</span>
              <strong>用户体验反馈分 (Feedback Score)</strong>
            </span>
            <span class="item-score">{{ breakdown.feedback !== null ? `${breakdown.feedback} 分` : '暂无数据' }}</span>
          </div>
          <el-progress
            :percentage="breakdown.feedback || 0"
            :stroke-width="8"
            color="#10b981"
            :show-text="false"
          />
          <span class="item-hint">方案卡片 1-5 星评分（显式主观分）与下单采纳/换一批动作（隐式转化分）分层融合</span>
        </div>

        <div class="breakdown-item" :class="{ 'is-disabled': breakdown.llmJudge === null }">
          <div class="item-header">
            <span class="item-name">
              <span class="weight-tag" :class="breakdown.llmJudge !== null ? 'llm-tag' : 'disabled-tag'">
                {{ breakdown.llmJudge !== null ? '10% 权重' : '未启用' }}
              </span>
              <strong>LLM 裁判盲评打分 (LLM Judge)</strong>
            </span>
            <span v-if="breakdown.llmJudge !== null" class="item-score">{{ breakdown.llmJudge }} 分</span>
            <span v-else class="item-score text-disabled">已关闭</span>
          </div>
          <el-progress
            :percentage="breakdown.llmJudge || 0"
            :stroke-width="8"
            :color="breakdown.llmJudge !== null ? '#8b5cf6' : '#cbd5e1'"
            :show-text="false"
          />
          <span class="item-hint">
            {{ breakdown.llmJudge !== null ? '基于评测 Prompt 从拟人性、方案合理性与礼貌度进行打分' : '裁判打分已关闭，权重已自动归一化分摊至客观规则与用户反馈' }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  overallScore: number
  breakdown: {
    rule: number
    feedback: number | null
    llmJudge: number | null
  }
}>()

const radius = 50
const circumference = 2 * Math.PI * radius

const strokeDashoffset = computed(() => {
  const progress = Math.min(100, Math.max(0, props.overallScore)) / 100
  return circumference * (1 - progress)
})

const scoreLevelClass = computed(() => {
  if (props.overallScore >= 90) return 'level-excellent'
  if (props.overallScore >= 80) return 'level-good'
  if (props.overallScore >= 60) return 'level-warning'
  return 'level-danger'
})

const scoreLevelText = computed(() => {
  if (props.overallScore >= 90) return '极佳 (A+)'
  if (props.overallScore >= 80) return '优良 (A)'
  if (props.overallScore >= 60) return '一般 (B)'
  return '亟需优化 (C)'
})
</script>

<style scoped>
.gauge-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}

.title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.level-badge {
  font-size: 11.5px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 9999px;
}

.level-excellent {
  background: #dcfce7;
  color: #15803d;
}

.level-good {
  background: #dbeafe;
  color: #1d4ed8;
}

.level-warning {
  background: #fef3c7;
  color: #b45309;
}

.level-danger {
  background: #fee2e2;
  color: #b91c1c;
}

.gauge-body {
  display: flex;
  align-items: center;
  gap: 32px;
}

.radial-box {
  position: relative;
  width: 140px;
  height: 140px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.radial-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.bg-circle {
  fill: none;
  stroke: #f1f5f9;
  stroke-width: 10;
}

.progress-circle {
  fill: none;
  stroke: #2563eb;
  stroke-width: 10;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.6s ease;
}

.score-center {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.score-number {
  font-size: 32px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1;
}

.score-unit {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

.breakdown-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.formula-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11px;
}

.formula-label {
  color: #64748b;
  font-weight: 600;
}

.formula-banner code {
  color: #0369a1;
  font-family: monospace;
  font-weight: 600;
}

.breakdown-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}

.item-name {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #334155;
}

.weight-tag {
  font-size: 10px;
  background: #eff6ff;
  color: #2563eb;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.feed-tag {
  background: #ecfdf5;
  color: #059669;
}

.llm-tag {
  background: #f5f3ff;
  color: #7c3aed;
}

.disabled-tag {
  background: #f1f5f9;
  color: #94a3b8;
}

.text-disabled {
  color: #94a3b8 !important;
  font-weight: 500 !important;
}

.breakdown-item.is-disabled {
  opacity: 0.85;
}

.item-score {
  font-family: monospace;
  font-weight: 700;
  color: #0f172a;
}

.item-hint {
  font-size: 11px;
  color: #94a3b8;
}
</style>
