<template>
  <div class="metrics-grid">
    <!-- Category 1: Planning Quality -->
    <div class="category-card">
      <div class="cat-header">
        <div class="cat-title">
          <el-icon><Compass /></el-icon>
          <span>规划质量 (Planning Quality)</span>
        </div>
        <span class="cat-badge badge-blue">意图与槽位</span>
      </div>

      <div class="metrics-list">
        <div
          v-for="m in metrics.planning"
          :key="m.name"
          class="metric-item"
        >
          <span class="metric-name">{{ m.name }}</span>
          <div class="metric-val-group">
            <span
              class="metric-number"
              :class="{ 'text-danger': m.isNegative && m.value > 5 }"
            >
              {{ m.value }}
            </span>
            <span class="metric-unit">{{ m.unit }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Category 2: Execution Quality -->
    <div class="category-card">
      <div class="cat-header">
        <div class="cat-title">
          <el-icon><Tickets /></el-icon>
          <span>执行质量 (Execution Quality)</span>
        </div>
        <span class="cat-badge badge-green">履约状态机</span>
      </div>

      <div class="metrics-list">
        <div
          v-for="m in metrics.execution"
          :key="m.name"
          class="metric-item"
        >
          <span class="metric-name">{{ m.name }}</span>
          <div class="metric-val-group">
            <span
              class="metric-number"
              :class="{ 'text-danger': m.isNegative && m.value > 3 }"
            >
              {{ m.value }}
            </span>
            <span class="metric-unit">{{ m.unit }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Category 3: User Experience -->
    <div class="category-card">
      <div class="cat-header">
        <div class="cat-title">
          <el-icon><Star /></el-icon>
          <span>用户体验 (User Experience)</span>
        </div>
        <span class="cat-badge badge-amber">30% 闭环权重</span>
      </div>

      <div class="metrics-list">
        <div
          v-for="m in metrics.experience"
          :key="m.name"
          class="metric-item"
        >
          <span class="metric-name">{{ m.name }}</span>
          <div class="metric-val-group">
            <span
              class="metric-number"
              :class="{ 'text-danger': m.isNegative && m.value > 5 }"
            >
              {{ m.value }}
            </span>
            <span class="metric-unit">{{ m.unit }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Category 4: Memory Quality -->
    <div class="category-card">
      <div class="cat-header">
        <div class="cat-title">
          <el-icon><Collection /></el-icon>
          <span>记忆质量 (Memory Quality)</span>
        </div>
        <span class="cat-badge badge-purple">L1-L3 召回</span>
      </div>

      <div class="metrics-list">
        <div
          v-for="m in metrics.memory"
          :key="m.name"
          class="metric-item"
        >
          <span class="metric-name">{{ m.name }}</span>
          <div class="metric-val-group">
            <span class="metric-number">{{ m.value }}</span>
            <span class="metric-unit">{{ m.unit }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface MetricEntry {
  name: string
  value: number
  unit: string
  isNegative?: boolean
  isRating?: boolean
}

defineProps<{
  metrics: {
    planning: MetricEntry[]
    execution: MetricEntry[]
    experience: MetricEntry[]
    memory: MetricEntry[]
  }
}>()
</script>

<style scoped>
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.category-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 18px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
}

.cat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
  margin-bottom: 12px;
}

.cat-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 700;
  color: #0f172a;
}

.cat-badge {
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
}

.badge-blue { background: #eff6ff; color: #2563eb; }
.badge-green { background: #ecfdf5; color: #059669; }
.badge-amber { background: #fffbeb; color: #d97706; }
.badge-purple { background: #f5f3ff; color: #7c3aed; }

.metrics-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
}

.metric-name {
  font-size: 12.5px;
  color: #475569;
}

.metric-val-group {
  display: flex;
  align-items: baseline;
  gap: 3px;
}

.metric-number {
  font-family: monospace;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.metric-number.text-danger {
  color: #dc2626;
}

.metric-unit {
  font-size: 11px;
  color: #94a3b8;
}
</style>
