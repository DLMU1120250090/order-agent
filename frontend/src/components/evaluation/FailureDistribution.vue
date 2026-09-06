<template>
  <div class="failure-card">
    <div class="card-header">
      <div class="title-group">
        <el-icon><Warning /></el-icon>
        <span class="header-title">9 大失败归因分类画像 (Failure Taxonomy)</span>
      </div>
      <span class="header-hint">基于评测链路自动聚类归因</span>
    </div>

    <div class="taxonomy-list">
      <div
        v-for="item in items"
        :key="item.key"
        class="taxonomy-row"
      >
        <div class="row-meta">
          <div class="name-box">
            <span class="tax-label">{{ item.label }}</span>
            <span class="tax-key">{{ item.key }}</span>
          </div>
          <div class="count-box">
            <span class="tax-count">{{ item.count }} 次</span>
            <span class="tax-pct">({{ calculatePct(item.count) }}%)</span>
          </div>
        </div>

        <div class="bar-container">
          <div
            class="bar-fill"
            :style="{ width: `${calculatePct(item.count)}%` }"
            :class="{ active: item.count > 0 }"
          ></div>
        </div>

        <div class="row-desc">
          <span>{{ item.desc }}</span>
          <router-link
            v-if="item.count > 0"
            :to="{ path: '/admin/traces', query: { q: item.key } }"
            class="trace-link"
          >
            排查相关 Trace →
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface FailureItem {
  key: string
  label: string
  count: number
  desc: string
}

const props = defineProps<{
  items: FailureItem[]
}>()

const totalFailures = computed(() => {
  return props.items.reduce((acc, cur) => acc + cur.count, 0)
})

function calculatePct(count: number): number {
  if (totalFailures.value === 0) return 0
  return Math.round((count / totalFailures.value) * 100)
}
</script>

<style scoped>
.failure-card {
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

.header-hint {
  font-size: 11.5px;
  color: #94a3b8;
}

.taxonomy-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.taxonomy-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 12px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  transition: all 0.15s ease;
}

.taxonomy-row:hover {
  background: #f1f5f9;
}

.row-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.name-box {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.tax-label {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.tax-key {
  font-family: monospace;
  font-size: 10.5px;
  color: #94a3b8;
}

.count-box {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.tax-count {
  font-family: monospace;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.tax-pct {
  font-size: 11px;
  color: #64748b;
}

.bar-container {
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: #94a3b8;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.bar-fill.active {
  background: #ef4444;
}

.row-desc {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

.trace-link {
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
}

.trace-link:hover {
  text-decoration: underline;
}
</style>
