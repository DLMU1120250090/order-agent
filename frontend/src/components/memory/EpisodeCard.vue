<template>
  <div class="episode-card">
    <div class="episode-top">
      <div class="route-box">
        <span class="transport-icon">{{ getModeIcon(episode.episode?.selected_plan?.mode) }}</span>
        <div class="route-text">
          <span class="route-city">{{ episode.episode?.context?.origin || '出发地' }}</span>
          <el-icon class="route-arrow"><Right /></el-icon>
          <span class="route-city">{{ episode.episode?.context?.destination || '目的地' }}</span>
        </div>
        <span v-if="episode.episode?.context?.purpose" class="purpose-tag">
          {{ episode.episode.context.purpose }}
        </span>
      </div>

      <div class="top-right">
        <span class="trip-id-badge">Trip #{{ episode.tripId || episode.id }}</span>
        <span class="time-txt">{{ formatDate(episode.createdAt) }}</span>
      </div>
    </div>

    <!-- Fulfillment Details -->
    <div class="fulfillment-box">
      <div class="plan-metric">
        <span class="metric-lbl">车次/航班</span>
        <span class="metric-val">{{ episode.episode?.selected_plan?.depart || '自选班次' }}</span>
      </div>
      <div class="plan-metric">
        <span class="metric-lbl">席位</span>
        <span class="metric-val">{{ episode.episode?.selected_plan?.seat || '二等座' }}</span>
      </div>
      <div class="plan-metric">
        <span class="metric-lbl">消费金额</span>
        <span class="metric-val price">¥{{ episode.episode?.selected_plan?.price || 0 }}</span>
      </div>
      <div class="plan-metric">
        <span class="metric-lbl">关联订单</span>
        <span class="metric-val code">{{ episode.episode?.selected_plan?.order_no || 'ORD-SYNC' }}</span>
      </div>
    </div>

    <!-- User Feedback / Outcome -->
    <div v-if="episode.episode?.outcome" class="outcome-row">
      <div class="rating-box">
        <span class="rating-lbl">行程履约评价:</span>
        <el-rate
          :model-value="episode.episode.outcome.rating || 5"
          disabled
          show-score
          text-color="#f59e0b"
          score-template="{value} 星"
        />
      </div>
      <div v-if="episode.episode.outcome.comment" class="comment-txt">
        "{{ episode.episode.outcome.comment }}"
      </div>
    </div>

    <!-- Derived Preferences Tags -->
    <div v-if="hasDerivedPrefs" class="derived-row">
      <span class="derived-title">沉淀记忆规则:</span>
      <div class="derived-tags">
        <span v-for="(reason, idx) in decisionReasons" :key="idx" class="derived-tag">
          {{ reason }}
        </span>
      </div>
    </div>

    <!-- Summary MD Toggle -->
    <div v-if="episode.summaryMd" class="summary-toggle-row">
      <button type="button" class="toggle-btn" @click="showSummary = !showSummary">
        <span>{{ showSummary ? '收起行程总结' : '查看完整行程叙事总结 (Narrative)' }}</span>
        <el-icon :class="{ rotated: showSummary }"><ArrowDown /></el-icon>
      </button>

      <div v-if="showSummary" class="summary-md-box">
        <pre class="md-content">{{ episode.summaryMd }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { TripEpisode } from '@/types/memory'

const props = defineProps<{
  episode: TripEpisode
}>()

const showSummary = ref(false)

const decisionReasons = computed(() => {
  const r = props.episode.episode?.decision_reason
  if (Array.isArray(r)) return r
  return ['偏好二等座靠窗', '优先下午发车车次']
})

const hasDerivedPrefs = computed(() => {
  return decisionReasons.value.length > 0
})

function getModeIcon(mode?: string): string {
  const m = (mode || '').toLowerCase()
  if (m.includes('flight') || m.includes('air') || m.includes('机')) return '✈️'
  if (m.includes('bus') || m.includes('大巴')) return '🚌'
  return '🚄'
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString()
}
</script>

<style scoped>
.episode-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  transition: all 0.2s ease;
}

.episode-card:hover {
  border-color: #cbd5e1;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.04);
}

.episode-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.route-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.transport-icon {
  font-size: 20px;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
}

.route-text {
  display: flex;
  align-items: center;
  gap: 6px;
}

.route-city {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.route-arrow {
  color: #94a3b8;
  font-size: 13px;
}

.purpose-tag {
  font-size: 11px;
  background: #eff6ff;
  color: #1d4ed8;
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 500;
}

.top-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trip-id-badge {
  font-family: monospace;
  font-size: 11px;
  font-weight: 600;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 2px 7px;
  border-radius: 4px;
  color: #64748b;
}

.time-txt {
  font-size: 11.5px;
  color: #94a3b8;
}

.fulfillment-box {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 14px;
  border: 1px solid #f1f5f9;
}

.plan-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-lbl {
  font-size: 10.5px;
  color: #94a3b8;
}

.metric-val {
  font-size: 12.5px;
  font-weight: 600;
  color: #1e293b;
}

.metric-val.price {
  color: #ea580c;
  font-weight: 700;
}

.metric-val.code {
  font-family: monospace;
  font-size: 11px;
  color: #64748b;
}

.outcome-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #fffbeb;
  border: 1px solid #fef3c7;
  border-radius: 6px;
  font-size: 12px;
}

.rating-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rating-lbl {
  font-weight: 600;
  color: #92400e;
}

.comment-txt {
  color: #b45309;
  font-style: italic;
}

.derived-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
}

.derived-title {
  color: #64748b;
  font-weight: 600;
  white-space: nowrap;
}

.derived-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.derived-tag {
  background: #f3e8ff;
  color: #7e22ce;
  border: 1px solid #f0abfc;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.summary-toggle-row {
  border-top: 1px solid #f1f5f9;
  padding-top: 8px;
}

.toggle-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  font-size: 11.5px;
  color: #2563eb;
  cursor: pointer;
  padding: 0;
}

.toggle-btn .el-icon {
  font-size: 11px;
  transition: transform 0.2s ease;
}

.toggle-btn .el-icon.rotated {
  transform: rotate(180deg);
}

.summary-md-box {
  margin-top: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 10px;
}

.md-content {
  margin: 0;
  font-family: inherit;
  font-size: 12px;
  color: #334155;
  white-space: pre-wrap;
  line-height: 1.5;
}
</style>
