<template>
  <div class="trace-workspace">
    <!-- Top Filter & Action Bar -->
    <header class="trace-topbar">
      <div class="topbar-left">
        <div class="page-title">
          <el-icon><DataLine /></el-icon>
          <span>可观测性工作台 (Agent Observability)</span>
        </div>

        <!-- Time Range Quick Filter -->
        <div class="range-chips">
          <button
            v-for="r in RANGES"
            :key="r.key"
            type="button"
            class="range-chip"
            :class="{ active: traceStore.filterQuickRange === r.key }"
            @click="handleRangeChange(r.key)"
          >
            {{ r.label }}
          </button>
        </div>

        <!-- Search Input -->
        <el-input
          v-model="traceStore.searchSessionId"
          placeholder="按 Session ID 或 Trace ID 检索"
          clearable
          size="small"
          class="search-input"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <!-- Only Unlabeled Checkbox -->
        <el-checkbox v-model="traceStore.onlyUnlabeled" size="small" @change="traceStore.fetchTraces">
          只看未标定
        </el-checkbox>

        <!-- Status Filter -->
        <el-select
          v-model="traceStore.statusFilter"
          size="small"
          class="status-select"
          placeholder="状态"
        >
          <el-option label="全部状态" value="ALL" />
          <el-option label="成功 (SUCCESS)" value="SUCCESS" />
          <el-option label="异常 (FAILED)" value="FAILED" />
        </el-select>
      </div>

      <div class="topbar-right">
        <el-button
          size="small"
          plain
          :loading="traceStore.isLoadingList"
          @click="traceStore.fetchTraces"
        >
          <el-icon><Refresh /></el-icon>
          刷新列表
        </el-button>

        <el-button
          size="small"
          type="primary"
          plain
          :disabled="!traceStore.selectedTraceId"
          @click="handleOpenReplay"
        >
          <el-icon><VideoPlay /></el-icon>
          一键 Replay 验证
        </el-button>

        <el-button
          size="small"
          type="primary"
          :disabled="!traceStore.selectedTraceId"
          @click="traceStore.showLabelModal = true"
        >
          <el-icon><EditPen /></el-icon>
          标定金标准
        </el-button>
      </div>
    </header>

    <!-- Main 2-Column Area -->
    <main class="trace-main-area">
      <!-- Left Sidebar: Trace Records List -->
      <aside class="trace-sidebar">
        <div class="sidebar-header">
          <span class="count-txt">共 {{ traceStore.filteredTraces.length }} 条记录</span>
        </div>

        <div v-loading="traceStore.isLoadingList" class="trace-list-container">
          <div v-if="traceStore.filteredTraces.length === 0" class="sidebar-empty">
            <el-empty description="未找到符合条件的 Trace 记录" :image-size="60" />
          </div>

          <div
            v-for="item in traceStore.filteredTraces"
            :key="item.traceId"
            class="trace-item-card"
            :class="{ active: item.traceId === traceStore.selectedTraceId }"
            @click="traceStore.selectTrace(item.traceId)"
          >
            <div class="card-top-row">
              <span class="item-trace-id">{{ item.traceId }}</span>
              <span class="item-status" :class="item.status.toLowerCase()">
                {{ item.status }}
              </span>
            </div>

            <div class="card-mid-row">
              <span class="item-session">Session: {{ item.sessionId }}</span>
            </div>

            <div class="card-bot-row">
              <span class="item-time">{{ formatTime(item.createdAt) }}</span>
              <div class="item-stats">
                <span class="stat-tag">{{ item.eventCount }} 节点</span>
                <span v-if="item.durationMs" class="stat-tag">{{ item.durationMs }}ms</span>
                <span v-if="item.expectedIntent || item.expectedClarifyAction" class="star-tag" title="已标定金标准">
                  ⭐
                </span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- Right Content: Timeline Waterfall & Details -->
      <section v-loading="traceStore.isLoadingDetail" class="trace-content-pane">
        <Timeline
          v-if="traceStore.currentTrace"
          :trace="traceStore.currentTrace"
          :events="traceStore.currentEvents"
          :summary="traceStore.summaryMetrics"
        />
        <div v-else class="empty-selection">
          <el-empty description="请从左侧选择一条 Trace 轨迹以查看执行链路" />
        </div>
      </section>
    </main>

    <!-- Sub Drawers / Modals -->
    <ReplayDrawer />
    <TraceLabelModal />
  </div>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useTraceStore } from '@/stores/trace'
import Timeline from '@/components/trace/Timeline.vue'
import ReplayDrawer from '@/components/trace/ReplayDrawer.vue'
import TraceLabelModal from '@/components/trace/TraceLabelModal.vue'

const route = useRoute()
const traceStore = useTraceStore()

const RANGES: { key: '1h' | 'today' | '7d' | '30d'; label: string }[] = [
  { key: '1h', label: '最近 1 小时' },
  { key: 'today', label: '今天' },
  { key: '7d', label: '最近 7 天' },
  { key: '30d', label: '最近 30 天' },
]

onMounted(async () => {
  await traceStore.fetchTraces()

  // Handle URL Query
  if (route.query.traceId && typeof route.query.traceId === 'string') {
    const tid = route.query.traceId
    await traceStore.selectTrace(tid)
    if (route.query.action === 'replay') {
      traceStore.runReplay(tid)
    }
  }
})

watch(
  () => route.query.traceId,
  async (newTid) => {
    if (newTid && typeof newTid === 'string' && newTid !== traceStore.selectedTraceId) {
      await traceStore.selectTrace(newTid)
      if (route.query.action === 'replay') {
        traceStore.runReplay(newTid)
      }
    }
  }
)

function handleRangeChange(rangeKey: '1h' | 'today' | '7d' | '30d') {
  traceStore.filterQuickRange = rangeKey
  traceStore.fetchTraces()
}

function handleOpenReplay() {
  if (!traceStore.selectedTraceId) return
  traceStore.runReplay(traceStore.selectedTraceId)
}

function formatTime(dateStr?: string): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<style scoped>
.trace-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: #f8fafc;
  overflow: hidden;
}

/* Topbar */
.trace-topbar {
  height: 52px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
  gap: 16px;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: nowrap;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
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
  white-space: nowrap;
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

.search-input {
  width: 220px;
}

.status-select {
  width: 120px;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* Main 2-Column */
.trace-main-area {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Sidebar List */
.trace-sidebar {
  width: 330px;
  background: #ffffff;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
}

.sidebar-header {
  height: 36px;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  padding: 0 14px;
  font-size: 11.5px;
  color: #94a3b8;
  font-weight: 600;
  background: #fafbfc;
}

.trace-list-container {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-empty {
  padding: 40px 0;
}

.trace-item-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trace-item-card:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}

.trace-item-card.active {
  border-color: #3b82f6;
  background: #eff6ff;
  box-shadow: 0 0 0 1px #3b82f6;
}

.card-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.item-trace-id {
  font-family: monospace;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.item-status {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.item-status.success {
  background: #dcfce7;
  color: #15803d;
}

.item-status.failed {
  background: #fee2e2;
  color: #b91c1c;
}

.card-mid-row {
  font-size: 11px;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-bot-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 2px;
}

.item-time {
  font-size: 11px;
  color: #94a3b8;
}

.item-stats {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stat-tag {
  font-size: 10px;
  background: #f1f5f9;
  color: #475569;
  padding: 1px 5px;
  border-radius: 4px;
}

.star-tag {
  font-size: 12px;
}

/* Content Pane */
.trace-content-pane {
  flex: 1;
  overflow: hidden;
  height: 100%;
}

.empty-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
</style>
