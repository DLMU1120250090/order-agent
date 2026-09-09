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
          :loading="traceStore.isReplaying"
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
        <!-- Sidebar Header: Total & Expand Controls -->
        <div class="sidebar-header">
          <div class="header-left">
            <span class="count-txt">共 {{ traceStore.filteredTraces.length }} 条记录</span>
            <span v-if="groupMode !== 'flat'" class="group-count-txt">· {{ groupCount }} 组</span>
          </div>
          <div v-if="groupMode !== 'flat'" class="header-actions">
            <button type="button" class="mini-action-btn" @click="toggleExpandAll">
              {{ allExpanded ? '全部折叠' : '全部展开' }}
            </button>
          </div>
        </div>

        <!-- 聚合模式切换栏 (方案三) -->
        <div class="group-mode-bar">
          <button
            type="button"
            class="group-mode-btn"
            :class="{ active: groupMode === 'flat' }"
            @click="groupMode = 'flat'"
          >
            平铺明细
          </button>
          <button
            type="button"
            class="group-mode-btn"
            :class="{ active: groupMode === 'session' }"
            @click="groupMode = 'session'"
          >
            按会话聚合
          </button>
          <button
            type="button"
            class="group-mode-btn"
            :class="{ active: groupMode === 'order' }"
            @click="groupMode = 'order'"
          >
            按订单聚合
          </button>
        </div>

        <div v-loading="traceStore.isLoadingList" class="trace-list-container">
          <div v-if="traceStore.filteredTraces.length === 0" class="sidebar-empty">
            <el-empty description="未找到符合条件的 Trace 记录" :image-size="60" />
          </div>

          <!-- 模式一：平铺明细 (Flat) -->
          <template v-else-if="groupMode === 'flat'">
            <div
              v-for="item in traceStore.filteredTraces"
              :key="item.traceId"
              class="trace-item-card"
              :class="{ active: item.traceId === traceStore.selectedTraceId }"
              @click="traceStore.selectTrace(item.traceId)"
            >
              <div class="card-top-row">
                <div class="id-user-group">
                  <span class="item-trace-id" :title="item.traceId">{{ item.traceId }}</span>
                  <span class="uid-badge">UID: {{ item.userId }}</span>
                </div>
                <span class="item-status" :class="item.status.toLowerCase()">
                  {{ item.status }}
                </span>
              </div>

              <div class="card-mid-row">
                <span class="item-session" :title="item.sessionId">Session: {{ item.sessionId }}</span>
                <span v-if="getPrimaryOrder(item)" class="item-order-tag" :title="getPrimaryOrder(item)">
                  🎫 {{ getPrimaryOrder(item) }}
                </span>
              </div>

              <div class="card-bot-row">
                <span class="item-time">📅 {{ formatDateTime(item.createdAt) }}</span>
                <div class="item-stats">
                  <span class="stat-tag">{{ item.eventCount }} 节点</span>
                  <span v-if="item.durationMs" class="stat-tag">{{ item.durationMs }}ms</span>
                  <span v-if="item.expectedIntent || item.expectedClarifyAction" class="star-tag" title="已标定金标准">
                    ⭐
                  </span>
                </div>
              </div>
            </div>
          </template>

          <!-- 模式二：按会话聚合 (Session) -->
          <template v-else-if="groupMode === 'session'">
            <div
              v-for="grp in sessionGroups"
              :key="grp.sessionId"
              class="trace-group-box"
            >
              <div
                class="group-header"
                @click="toggleGroup('sess_' + grp.sessionId)"
              >
                <div class="group-title-row">
                  <el-icon class="arrow-icon" :class="{ rotated: isGroupExpanded('sess_' + grp.sessionId) }">
                    <ArrowRight />
                  </el-icon>
                  <span class="group-icon">💬</span>
                  <span class="group-title-text" :title="grp.sessionId">会话: {{ formatShortId(grp.sessionId, 12) }}</span>
                  <span class="uid-badge">UID: {{ grp.userId }}</span>
                </div>
                <div class="group-meta-row">
                  <span class="group-count-badge">{{ grp.traces.length }} 轮 Trace</span>
                  <span class="group-time-text">{{ formatTime(grp.latestTime) }}</span>
                </div>
              </div>

              <div v-show="isGroupExpanded('sess_' + grp.sessionId)" class="group-children">
                <div
                  v-for="(item, idx) in grp.traces"
                  :key="item.traceId"
                  class="group-item-card"
                  :class="{ active: item.traceId === traceStore.selectedTraceId }"
                  @click.stop="traceStore.selectTrace(item.traceId)"
                >
                  <div class="group-item-top">
                    <div class="item-turn-pill">#{{ idx + 1 }}</div>
                    <span class="item-trace-id mini" :title="item.traceId">{{ item.traceId }}</span>
                    <span class="item-status mini" :class="item.status.toLowerCase()">
                      {{ item.status }}
                    </span>
                  </div>
                  <div class="group-item-bot">
                    <span class="item-time">📅 {{ formatDateTime(item.createdAt) }}</span>
                    <div class="item-stats">
                      <span v-if="getPrimaryOrder(item)" class="item-order-tag mini" :title="getPrimaryOrder(item)">
                        🎫 {{ getPrimaryOrder(item).slice(-8) }}
                      </span>
                      <span class="stat-tag">{{ item.eventCount }} 节点</span>
                      <span v-if="item.durationMs" class="stat-tag">{{ item.durationMs }}ms</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- 模式三：按订单聚合 (Order) -->
          <template v-else-if="groupMode === 'order'">
            <div
              v-for="grp in orderGroups"
              :key="grp.key"
              class="trace-group-box"
            >
              <div
                class="group-header"
                @click="toggleGroup('ord_' + grp.key)"
              >
                <div class="group-title-row">
                  <el-icon class="arrow-icon" :class="{ rotated: isGroupExpanded('ord_' + grp.key) }">
                    <ArrowRight />
                  </el-icon>
                  <span class="group-icon">{{ grp.isUnbound ? '💭' : '🎫' }}</span>
                  <span class="group-title-text" :title="grp.orderNo">
                    {{ grp.isUnbound ? '咨询与规划 (未成单)' : '订单: ' + grp.orderNo }}
                  </span>
                  <span v-if="!grp.isUnbound" class="uid-badge">UID: {{ grp.userId }}</span>
                </div>
                <div class="group-meta-row">
                  <span class="group-count-badge">{{ grp.traces.length }} 条 Trace</span>
                  <span class="group-time-text">{{ formatTime(grp.latestTime) }}</span>
                </div>
              </div>

              <div v-show="isGroupExpanded('ord_' + grp.key)" class="group-children">
                <div
                  v-for="item in grp.traces"
                  :key="item.traceId"
                  class="group-item-card"
                  :class="{ active: item.traceId === traceStore.selectedTraceId }"
                  @click.stop="traceStore.selectTrace(item.traceId)"
                >
                  <div class="group-item-top">
                    <div class="id-user-group">
                      <span class="item-trace-id mini" :title="item.traceId">{{ item.traceId }}</span>
                      <span class="uid-badge">UID: {{ item.userId }}</span>
                    </div>
                    <span class="item-status mini" :class="item.status.toLowerCase()">
                      {{ item.status }}
                    </span>
                  </div>
                  <div v-if="grp.isUnbound" class="group-item-mid">
                    <span class="item-session mini" :title="item.sessionId">Session: {{ item.sessionId }}</span>
                  </div>
                  <div class="group-item-bot">
                    <span class="item-time">📅 {{ formatDateTime(item.createdAt) }}</span>
                    <div class="item-stats">
                      <span class="stat-tag">{{ item.eventCount }} 节点</span>
                      <span v-if="item.durationMs" class="stat-tag">{{ item.durationMs }}ms</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useTraceStore } from '@/stores/trace'
import { formatBeijingDateTime, formatBeijingTime } from '@/utils/time'
import { extractOrderNos, getPrimaryOrderNo, formatShortId } from '@/utils/trace'
import type { TraceRowOut } from '@/types/trace'
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

// 聚合维度模式
type GroupMode = 'flat' | 'session' | 'order'
const groupMode = ref<GroupMode>('flat')
const expandedGroupKeys = ref<Set<string>>(new Set())

interface SessionGroup {
  sessionId: string
  userId: number
  traces: TraceRowOut[]
  latestTime: string
}

interface OrderGroup {
  key: string
  orderNo: string
  isUnbound: boolean
  userId: number
  traces: TraceRowOut[]
  latestTime: string
}

// 按会话聚合
const sessionGroups = computed<SessionGroup[]>(() => {
  const map = new Map<string, SessionGroup>()
  for (const t of traceStore.filteredTraces) {
    const sid = t.sessionId || 'UNKNOWN_SESSION'
    if (!map.has(sid)) {
      map.set(sid, {
        sessionId: sid,
        userId: t.userId,
        traces: [],
        latestTime: t.createdAt,
      })
    }
    map.get(sid)!.traces.push(t)
  }
  return Array.from(map.values())
})

// 按订单聚合
const orderGroups = computed<OrderGroup[]>(() => {
  const map = new Map<string, OrderGroup>()
  const unboundTraces: TraceRowOut[] = []
  let unboundLatest = ''

  for (const t of traceStore.filteredTraces) {
    const orders = extractOrderNos(t)
    if (orders.length === 0) {
      unboundTraces.push(t)
      if (!unboundLatest) unboundLatest = t.createdAt
    } else {
      for (const ono of orders) {
        if (!map.has(ono)) {
          map.set(ono, {
            key: ono,
            orderNo: ono,
            isUnbound: false,
            userId: t.userId,
            traces: [],
            latestTime: t.createdAt,
          })
        }
        map.get(ono)!.traces.push(t)
      }
    }
  }

  const res = Array.from(map.values())
  res.sort((a, b) => new Date(b.latestTime).getTime() - new Date(a.latestTime).getTime())

  if (unboundTraces.length > 0) {
    res.push({
      key: 'UNBOUND',
      orderNo: '未成单咨询与规划',
      isUnbound: true,
      userId: unboundTraces[0]?.userId || 0,
      traces: unboundTraces,
      latestTime: unboundLatest || unboundTraces[0]?.createdAt || '',
    })
  }
  return res
})

const groupCount = computed(() => {
  return groupMode.value === 'session' ? sessionGroups.value.length : orderGroups.value.length
})

function isGroupExpanded(key: string): boolean {
  return expandedGroupKeys.value.has(key)
}

function toggleGroup(key: string) {
  if (expandedGroupKeys.value.has(key)) {
    expandedGroupKeys.value.delete(key)
  } else {
    expandedGroupKeys.value.add(key)
  }
}

const allExpanded = computed(() => {
  const keys = groupMode.value === 'session'
    ? sessionGroups.value.map(g => 'sess_' + g.sessionId)
    : orderGroups.value.map(g => 'ord_' + g.key)
  return keys.length > 0 && keys.every(k => expandedGroupKeys.value.has(k))
})

function toggleExpandAll() {
  const keys = groupMode.value === 'session'
    ? sessionGroups.value.map(g => 'sess_' + g.sessionId)
    : orderGroups.value.map(g => 'ord_' + g.key)
  if (allExpanded.value) {
    expandedGroupKeys.value.clear()
  } else {
    keys.forEach(k => expandedGroupKeys.value.add(k))
  }
}

// 选中 Trace 时自动展开对应分组
watch(
  () => [traceStore.selectedTraceId, groupMode.value],
  ([newTid]) => {
    if (!newTid || typeof newTid !== 'string') return
    if (groupMode.value === 'session') {
      const grp = sessionGroups.value.find(g => g.traces.some(t => t.traceId === newTid))
      if (grp) expandedGroupKeys.value.add('sess_' + grp.sessionId)
    } else if (groupMode.value === 'order') {
      const grp = orderGroups.value.find(g => g.traces.some(t => t.traceId === newTid))
      if (grp) expandedGroupKeys.value.add('ord_' + grp.key)
    }
  },
  { immediate: true }
)

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

async function handleOpenReplay() {
  if (!traceStore.selectedTraceId) return
  try {
    await traceStore.runReplay(traceStore.selectedTraceId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || err?.message || 'Replay 执行失败')
  }
}

function formatDateTime(dateStr?: string): string {
  return formatBeijingDateTime(dateStr)
}

function formatTime(dateStr?: string): string {
  return formatBeijingTime(dateStr)
}

function getPrimaryOrder(item: TraceRowOut): string {
  return getPrimaryOrderNo(item) || ''
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
  width: 360px;
  background: #ffffff;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
}

.sidebar-header {
  height: 38px;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  background: #fafbfc;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}

.count-txt {
  font-size: 11.5px;
  color: #64748b;
  font-weight: 600;
}

.group-count-txt {
  font-size: 11.5px;
  color: #94a3b8;
}

.mini-action-btn {
  border: none;
  background: transparent;
  color: #3b82f6;
  font-size: 11px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.15s;
}

.mini-action-btn:hover {
  background: #eff6ff;
}

/* Group Mode Bar */
.group-mode-bar {
  display: flex;
  align-items: center;
  background: #f1f5f9;
  border-radius: 6px;
  margin: 8px 10px 4px 10px;
  padding: 2px;
  gap: 2px;
}

.group-mode-btn {
  flex: 1;
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 11.5px;
  font-weight: 600;
  padding: 4px 0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: center;
}

.group-mode-btn.active {
  background: #ffffff;
  color: #2563eb;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.group-mode-btn:hover:not(.active) {
  color: #0f172a;
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

/* Cards (Flat Mode) */
.trace-item-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 9px 11px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
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
  gap: 6px;
}

.id-user-group {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
}

.item-trace-id {
  font-family: monospace;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.uid-badge {
  font-size: 10px;
  font-weight: 700;
  color: #2563eb;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  padding: 0 4px;
  border-radius: 3px;
  white-space: nowrap;
  flex-shrink: 0;
}

.item-status {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  flex-shrink: 0;
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
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  white-space: nowrap;
}

.item-session {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.item-order-tag {
  font-size: 10px;
  font-weight: 600;
  color: #b45309;
  background: #fef3c7;
  border: 1px solid #fde68a;
  padding: 0 4px;
  border-radius: 3px;
  white-space: nowrap;
  flex-shrink: 0;
}

.card-bot-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 2px;
}

.item-time {
  font-size: 10.5px;
  color: #64748b;
  font-weight: 500;
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

/* Grouping Box (Session & Order Mode) */
.trace-group-box {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 6px;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.trace-group-box:hover {
  border-color: #cbd5e1;
}

.group-header {
  padding: 8px 10px;
  background: #f8fafc;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 3px;
  user-select: none;
  transition: background 0.15s;
}

.group-header:hover {
  background: #f1f5f9;
}

.group-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.arrow-icon {
  font-size: 11px;
  color: #94a3b8;
  transition: transform 0.2s ease;
}

.arrow-icon.rotated {
  transform: rotate(90deg);
}

.group-icon {
  font-size: 12px;
}

.group-title-text {
  font-size: 12px;
  font-weight: 700;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.group-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-left: 21px;
}

.group-count-badge {
  font-size: 10px;
  color: #475569;
  background: #e2e8f0;
  padding: 0 5px;
  border-radius: 10px;
  font-weight: 500;
}

.group-time-text {
  font-size: 10px;
  color: #94a3b8;
}

.group-children {
  padding: 6px 8px;
  background: #fafbfc;
  border-top: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.group-item-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 7px 9px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.group-item-card:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}

.group-item-card.active {
  border-color: #3b82f6;
  background: #eff6ff;
  box-shadow: 0 0 0 1px #3b82f6;
}

.group-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.item-turn-pill {
  font-size: 9.5px;
  font-weight: 700;
  color: #64748b;
  background: #f1f5f9;
  padding: 0 4px;
  border-radius: 3px;
}

.item-trace-id.mini {
  font-size: 11px;
  max-width: 170px;
}

.item-status.mini {
  font-size: 9px;
  padding: 0 4px;
}

.group-item-mid {
  font-size: 10px;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-session.mini {
  font-size: 10px;
}

.group-item-bot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  margin-top: 1px;
}

.item-order-tag.mini {
  font-size: 9.5px;
  padding: 0 3px;
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
