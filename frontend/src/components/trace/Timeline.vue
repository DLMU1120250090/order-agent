<template>
  <div class="timeline-container">
    <!-- Trace Summary Card -->
    <div v-if="trace" class="summary-card">
      <div class="summary-top">
        <div class="summary-left">
          <div class="trace-id-title">
            <span class="lbl">Trace</span>
            <span class="id-val">{{ trace.traceId }}</span>
            <el-button size="small" link type="primary" @click="copy(trace.traceId)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
          <div class="session-crumb">
            <span>会话 ID: <strong>{{ trace.sessionId }}</strong></span>
            <span>·</span>
            <span>用户 ID: <strong>{{ trace.userId }}</strong></span>
            <span>·</span>
            <span>时间: <strong>{{ formatDate(trace.createdAt) }}</strong></span>
          </div>
        </div>

        <div class="summary-right">
          <span class="status-badge" :class="trace.status.toLowerCase()">
            {{ trace.status }}
          </span>
        </div>
      </div>

      <!-- Metrics Gantt Row -->
      <div class="metrics-grid">
        <div class="metric-box">
          <span class="metric-num">{{ summary.eventCount }}</span>
          <span class="metric-lbl">轨迹节点总数</span>
        </div>
        <div class="metric-box">
          <span class="metric-num">{{ summary.totalLatency }}<small>ms</small></span>
          <span class="metric-lbl">端到端总耗时</span>
        </div>
        <div class="metric-box">
          <span class="metric-num">{{ summary.totalTokens || 'N/A' }}</span>
          <span class="metric-lbl">LLM Token 消耗</span>
        </div>
        <div class="metric-box">
          <div class="agents-tags">
            <span v-for="agent in summary.agents" :key="agent" class="agent-tag">
              {{ agent }}
            </span>
            <span v-if="summary.agents.length === 0" class="empty-txt">默认编排器</span>
          </div>
          <span class="metric-lbl">参与智能体</span>
        </div>
      </div>

      <!-- Expected Golden Label Banner if Labeled -->
      <div v-if="trace.expectedIntent || trace.expectedClarifyAction" class="golden-banner">
        <span class="golden-badge">⭐ 已标定金标准</span>
        <span v-if="trace.expectedIntent" class="golden-item">
          期望意图: <strong>{{ trace.expectedIntent }}</strong>
        </span>
        <span v-if="trace.expectedClarifyAction" class="golden-item">
          期望动作: <strong>{{ trace.expectedClarifyAction }}</strong>
        </span>
        <span v-if="trace.labelNote" class="golden-item">
          备注: <em>{{ trace.labelNote }}</em>
        </span>
      </div>
    </div>

    <!-- Phase Filter Bar -->
    <div class="phase-filter-bar">
      <span class="filter-lbl">阶段过滤:</span>
      <div class="phase-chips">
        <button
          v-for="p in PHASES"
          :key="p.key"
          type="button"
          class="phase-chip"
          :class="{ active: selectedPhase === p.key }"
          @click="selectedPhase = p.key"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="filter-actions">
        <el-button size="small" plain @click="expandAll">全部展开</el-button>
        <el-button size="small" plain @click="collapseAll">全部折叠</el-button>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="filteredEvents.length === 0" class="empty-timeline">
      <el-empty description="该阶段无匹配的轨迹事件" :image-size="80" />
    </div>

    <!-- Waterfall Timeline -->
    <div v-else class="waterfall-stream">
      <div
        v-for="ev in filteredEvents"
        :id="`timeline-step-${ev.stepOrder}`"
        :key="ev.stepOrder || ev.eventId"
        class="waterfall-node"
        :class="{
          'has-error': !!ev.errorMessage,
          'is-expanded': expandedSteps.has(ev.stepOrder),
          'is-highlighted': traceStore.highlightedStepOrder === ev.stepOrder,
        }"
      >
        <!-- Node Left Pillar -->
        <div class="node-pillar">
          <div class="node-bullet" :class="phaseClass(ev.phase)">
            {{ ev.stepOrder }}
          </div>
          <div class="node-line"></div>
        </div>

        <!-- Node Card -->
        <div class="node-card">
          <div class="node-header" @click="toggleStep(ev.stepOrder)">
            <div class="node-title-group">
              <span class="phase-pill" :class="phaseClass(ev.phase)">{{ ev.phase || 'FLOW' }}</span>
              <span class="event-name">{{ ev.eventType }}</span>
              <span v-if="ev.agentName" class="agent-sub-tag">@{{ ev.agentName }}</span>
            </div>

            <div class="node-meta-group">
              <span v-if="ev.latencyMs" class="latency-txt">
                <el-icon><Timer /></el-icon> {{ ev.latencyMs }} ms
              </span>
              <span v-if="ev.totalTokens" class="tokens-txt">
                {{ ev.totalTokens }} tok
              </span>
              <el-icon class="expand-icon" :class="{ rotated: expandedSteps.has(ev.stepOrder) }">
                <ArrowRight />
              </el-icon>
            </div>
          </div>

          <!-- Error Alert Banner -->
          <div v-if="ev.errorMessage" class="error-banner">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ ev.errorMessage }}</span>
          </div>

          <!-- Expanded Payload Details -->
          <div v-if="expandedSteps.has(ev.stepOrder)" class="node-details">
            <!-- Key Decision Summary -->
            <div v-if="ev.decision" class="detail-section">
              <div class="section-title">智能体决策产出 (Decision)</div>
              <pre class="code-block json">{{ formatJson(ev.decision) }}</pre>
            </div>

            <!-- Inferred Fields & Memory Info -->
            <div v-if="ev.inferredFields && Object.keys(ev.inferredFields).length > 0" class="detail-section">
              <div class="section-title">记忆推理补全 (Inferred Fields)</div>
              <div class="inferred-chips">
                <span v-for="(v, k) in ev.inferredFields" :key="k" class="inferred-chip">
                  <strong>{{ k }}</strong>: {{ v }}
                </span>
              </div>
            </div>

            <div v-if="ev.memorySources && ev.memorySources.length > 0" class="detail-section">
              <div class="section-title">命中的记忆源 (Memory Sources)</div>
              <div class="memory-chips">
                <span v-for="src in ev.memorySources" :key="src" class="mem-src-chip">
                  {{ src }}
                </span>
              </div>
            </div>

            <!-- Input & Output Payload Tabs -->
            <div class="detail-section">
              <el-tabs type="border-card" class="payload-tabs">
                <el-tab-pane label="输出载荷 (Output Payload)" v-if="ev.outputPayload">
                  <pre class="code-block">{{ formatJson(ev.outputPayload) }}</pre>
                </el-tab-pane>
                <el-tab-pane label="输入载荷 (Input Payload)" v-if="ev.inputPayload">
                  <pre class="code-block">{{ formatJson(ev.inputPayload) }}</pre>
                </el-tab-pane>
                <el-tab-pane label="完整原始事件 (Raw Event)">
                  <pre class="code-block">{{ formatJson(ev) }}</pre>
                </el-tab-pane>
              </el-tabs>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useTraceStore } from '@/stores/trace'
import type { TraceRowOut, TraceEvent } from '@/types/trace'
import { formatBeijingDateTime } from '@/utils/time'

const traceStore = useTraceStore()

const props = defineProps<{
  trace: TraceRowOut
  events: TraceEvent[]
  summary: {
    eventCount: number
    totalTokens: number
    totalLatency: number
    agents: string[]
    hasError: boolean
  }
}>()

const PHASES = [
  { key: 'ALL', label: '全部阶段' },
  { key: 'HTTP', label: 'HTTP 接入' },
  { key: 'INTENT', label: '意图/澄清' },
  { key: 'MEMORY', label: '记忆检索' },
  { key: 'PLAN', label: '行程规划' },
  { key: 'ORDER', label: '订单/履约' },
  { key: 'TASK', label: '异步任务' },
]

const selectedPhase = ref('ALL')
const expandedSteps = ref<Set<number>>(new Set([1, 2, 3]))

// 监听高亮节点指令（来自 Replay 抽屉溯源点击）
watch(
  () => traceStore.highlightedStepOrder,
  (step) => {
    if (step !== null && step !== undefined) {
      selectedPhase.value = 'ALL'
      expandedSteps.value.add(step)
      nextTick(() => {
        const el = document.getElementById(`timeline-step-${step}`)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      })
    }
  }
)

const filteredEvents = computed(() => {
  if (selectedPhase.value === 'ALL') return props.events
  return props.events.filter((e) => {
    const p = (e.phase || '').toUpperCase()
    if (selectedPhase.value === 'PLAN') return p === 'PLAN' || p === 'PLANNING'
    return p === selectedPhase.value
  })
})

function toggleStep(step: number) {
  if (expandedSteps.value.has(step)) {
    expandedSteps.value.delete(step)
  } else {
    expandedSteps.value.add(step)
  }
}

function expandAll() {
  expandedSteps.value = new Set(props.events.map(e => e.stepOrder))
}

function collapseAll() {
  expandedSteps.value = new Set()
}

function phaseClass(phase?: string): string {
  switch ((phase || '').toUpperCase()) {
    case 'HTTP': return 'phase-http'
    case 'INTENT': return 'phase-intent'
    case 'PLAN':
    case 'PLANNING': return 'phase-plan'
    case 'ORDER': return 'phase-order'
    case 'TASK': return 'phase-task'
    case 'MEMORY': return 'phase-memory'
    default: return 'phase-default'
  }
}

function formatJson(data: any): string {
  if (typeof data === 'string') {
    try {
      return JSON.stringify(JSON.parse(data), null, 2)
    } catch {
      return data
    }
  }
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function formatDate(dateStr?: string): string {
  return formatBeijingDateTime(dateStr)
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('Trace ID 已复制')
  } catch {
    ElMessage.info(text)
  }
}
</script>

<style scoped>
.timeline-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding: 16px 20px;
  gap: 16px;
  background: #f8fafc;
}

/* Summary Card */
.summary-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
}

.summary-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
}

.trace-id-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 4px;
}

.trace-id-title .lbl {
  color: #64748b;
}

.trace-id-title .id-val {
  font-family: monospace;
  color: #0f172a;
}

.session-crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #64748b;
}

.session-crumb strong {
  color: #334155;
}

.status-badge {
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 9999px;
  text-transform: uppercase;
}

.status-badge.success {
  background: #dcfce7;
  color: #15803d;
}

.status-badge.failed {
  background: #fee2e2;
  color: #b91c1c;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  background: #f8fafc;
  border-radius: 10px;
  padding: 12px 16px;
}

.metric-box {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-num {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.metric-num small {
  font-size: 12px;
  font-weight: 500;
  color: #64748b;
  margin-left: 2px;
}

.metric-lbl {
  font-size: 11px;
  color: #94a3b8;
}

.agents-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 24px;
  align-items: center;
}

.agent-tag {
  font-size: 11px;
  background: #e0f2fe;
  color: #0369a1;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.empty-txt {
  font-size: 11px;
  color: #94a3b8;
}

.golden-banner {
  margin-top: 12px;
  padding: 8px 12px;
  background: #fffbeb;
  border: 1px solid #fef3c7;
  border-radius: 8px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
}

.golden-badge {
  font-weight: 700;
  color: #b45309;
}

.golden-item {
  color: #78350f;
}

/* Phase Filter Bar */
.phase-filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 8px 14px;
}

.filter-lbl {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-right: 8px;
}

.phase-chips {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.phase-chip {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 3px 10px;
  border-radius: 9999px;
  font-size: 12px;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s ease;
}

.phase-chip:hover {
  background: #e2e8f0;
}

.phase-chip.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
  font-weight: 600;
}

.filter-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Waterfall Stream */
.waterfall-stream {
  display: flex;
  flex-direction: column;
}

.waterfall-node {
  display: flex;
  gap: 14px;
}

.node-pillar {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 28px;
  flex-shrink: 0;
}

.node-bullet {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: monospace;
  font-size: 11px;
  font-weight: 700;
  z-index: 1;
  box-shadow: 0 0 0 2px #ffffff;
}

.node-line {
  flex: 1;
  width: 2px;
  background: #e2e8f0;
  margin: 4px 0;
  min-height: 20px;
}

.node-card {
  flex: 1;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  margin-bottom: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  transition: border-color 0.2s ease;
}

.waterfall-node.has-error .node-card {
  border-color: #fca5a5;
}

.waterfall-node.is-expanded .node-card {
  border-color: #93c5fd;
}

.waterfall-node.is-highlighted .node-card {
  border-color: #2563eb !important;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.28) !important;
  animation: nodePulse 1.6s ease-in-out infinite alternate;
}

@keyframes nodePulse {
  0% {
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
    border-color: #3b82f6;
  }
  100% {
    box-shadow: 0 0 0 8px rgba(37, 99, 235, 0.45);
    border-color: #1d4ed8;
  }
}

.node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}

.node-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.phase-pill {
  font-size: 10.5px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
}

.phase-http { background: #f1f5f9; color: #475569; }
.phase-intent { background: #e0e7ff; color: #4338ca; }
.phase-plan { background: #dbeafe; color: #1d4ed8; }
.phase-order { background: #dcfce7; color: #15803d; }
.phase-task { background: #fef3c7; color: #b45309; }
.phase-memory { background: #f3e8ff; color: #7e22ce; }
.phase-default { background: #f1f5f9; color: #64748b; }

.event-name {
  font-family: monospace;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.agent-sub-tag {
  font-size: 11px;
  color: #64748b;
  background: #f8fafc;
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid #f1f5f9;
}

.node-meta-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.latency-txt, .tokens-txt {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: monospace;
  font-size: 11px;
  color: #64748b;
}

.expand-icon {
  font-size: 12px;
  color: #94a3b8;
  transition: transform 0.2s ease;
}

.expand-icon.rotated {
  transform: rotate(90deg);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #fee2e2;
  color: #991b1b;
  padding: 6px 14px;
  font-size: 12px;
  border-top: 1px solid #fca5a5;
}

.node-details {
  padding: 12px 14px;
  background: #f8fafc;
  border-top: 1px solid #f1f5f9;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.section-title {
  font-size: 11.5px;
  font-weight: 600;
  color: #475569;
}

.code-block {
  font-family: monospace;
  font-size: 11.5px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 10px;
  margin: 0;
  max-height: 240px;
  overflow-y: auto;
  color: #1e293b;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-all;
}

.inferred-chips, .memory-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.inferred-chip {
  font-size: 11px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  padding: 2px 8px;
  border-radius: 4px;
  color: #334155;
}

.mem-src-chip {
  font-size: 11px;
  background: #f3e8ff;
  color: #6b21a8;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}

.payload-tabs {
  margin-top: 4px;
}

.empty-timeline {
  background: #ffffff;
  border-radius: 12px;
  padding: 40px;
  border: 1px solid #e2e8f0;
}
</style>
