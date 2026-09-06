<template>
  <div class="trace-preview-panel">
    <!-- Trace Meta Header -->
    <div class="trace-meta-box">
      <div class="meta-row">
        <span class="meta-label">Trace ID</span>
        <div class="trace-id-group">
          <span class="trace-id-text">{{ runtimeStore.activeTraceId || '等待对话触发...' }}</span>
          <el-button
            v-if="runtimeStore.activeTraceId"
            size="small"
            link
            type="primary"
            @click="copyTraceId"
          >
            <el-icon><CopyDocument /></el-icon>
          </el-button>
        </div>
      </div>

      <div v-if="runtimeStore.traceDetail" class="stats-row">
        <div class="stat-item">
          <span class="stat-num">{{ runtimeStore.events.length }}</span>
          <span class="stat-lbl">轨迹事件</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-num">{{ runtimeStore.totalLatencyMs }}<small>ms</small></span>
          <span class="stat-lbl">端到端耗时</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span
            class="stat-status"
            :class="(runtimeStore.traceDetail.status || 'SUCCESS').toLowerCase()"
          >
            {{ runtimeStore.traceDetail.status || 'SUCCESS' }}
          </span>
          <span class="stat-lbl">执行状态</span>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="runtimeStore.events.length === 0" class="empty-state">
      <div class="empty-icon">🛰️</div>
      <div class="empty-title">暂无 Trace 轨迹数据</div>
      <div class="empty-desc">在左侧发送消息后，可观测引擎将自动捕获并渲染全链路日志喵~</div>
    </div>

    <!-- Compact Events Timeline -->
    <div v-else class="events-scroll">
      <div class="events-list">
        <div
          v-for="ev in runtimeStore.events"
          :key="ev.stepOrder || ev.eventId"
          class="event-item"
        >
          <div class="event-header" @click="toggleExpand(ev.stepOrder)">
            <div class="event-left">
              <span class="event-order">#{{ ev.stepOrder }}</span>
              <span class="phase-tag" :class="phaseClass(ev.phase)">{{ ev.phase || 'AGENT' }}</span>
              <span class="event-type">{{ ev.eventType }}</span>
            </div>
            <div class="event-right">
              <span v-if="ev.latencyMs" class="latency-text">{{ ev.latencyMs }}ms</span>
              <el-icon class="expand-arrow" :class="{ rotated: expandedSteps.has(ev.stepOrder) }">
                <ArrowRight />
              </el-icon>
            </div>
          </div>

          <!-- Expanded Payload Viewer -->
          <div v-if="expandedSteps.has(ev.stepOrder)" class="event-body">
            <div v-if="ev.agentName" class="body-row">
              <span class="body-lbl">Agent:</span>
              <span class="body-val">{{ ev.agentName }}</span>
            </div>
            <div v-if="ev.decision" class="body-row">
              <span class="body-lbl">Decision:</span>
              <pre class="body-json">{{ formatJson(ev.decision) }}</pre>
            </div>
            <div v-if="ev.outputPayload" class="body-row">
              <span class="body-lbl">Output:</span>
              <pre class="body-json">{{ formatJson(ev.outputPayload) }}</pre>
            </div>
            <div v-if="ev.errorMessage" class="body-row error-row">
              <span class="body-lbl">Error:</span>
              <span class="body-val error-text">{{ ev.errorMessage }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Actions -->
    <div class="actions-footer">
      <el-button
        type="primary"
        class="full-btn"
        :disabled="!runtimeStore.activeTraceId"
        @click="jumpToTraceDetail"
      >
        <el-icon><View /></el-icon>
        在可观测工作台查看完整 Trace
      </el-button>

      <el-button
        plain
        class="full-btn sub-btn"
        :disabled="!runtimeStore.activeTraceId"
        @click="jumpToReplay"
      >
        <el-icon><VideoPlay /></el-icon>
        一键发起 Replay 离线验证
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useRuntimeStore } from '@/stores/runtime'

const router = useRouter()
const runtimeStore = useRuntimeStore()
const expandedSteps = ref<Set<number>>(new Set())

function toggleExpand(step: number) {
  if (expandedSteps.value.has(step)) {
    expandedSteps.value.delete(step)
  } else {
    expandedSteps.value.add(step)
  }
}

function phaseClass(phase: string): string {
  switch ((phase || '').toUpperCase()) {
    case 'HTTP': return 'phase-http'
    case 'INTENT': return 'phase-intent'
    case 'PLAN':
    case 'PLANNING': return 'phase-plan'
    case 'ORDER':
    case 'TASK': return 'phase-order'
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

async function copyTraceId() {
  if (!runtimeStore.activeTraceId) return
  try {
    await navigator.clipboard.writeText(runtimeStore.activeTraceId)
    ElMessage.success('Trace ID 已复制到剪贴板')
  } catch {
    ElMessage.info(runtimeStore.activeTraceId)
  }
}

function jumpToTraceDetail() {
  if (!runtimeStore.activeTraceId) return
  router.push({
    path: '/admin/traces',
    query: { traceId: runtimeStore.activeTraceId },
  })
}

function jumpToReplay() {
  if (!runtimeStore.activeTraceId) return
  router.push({
    path: '/admin/traces',
    query: { traceId: runtimeStore.activeTraceId, action: 'replay' },
  })
}
</script>

<style scoped>
.trace-preview-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  gap: 12px;
  overflow: hidden;
}

.trace-meta-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
  flex-shrink: 0;
}

.meta-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: #94a3b8;
}

.trace-id-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.trace-id-text {
  font-family: monospace;
  font-size: 12px;
  color: #2563eb;
  font-weight: 600;
  word-break: break-all;
}

.stats-row {
  display: flex;
  align-items: center;
  justify-content: space-around;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #e2e8f0;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stat-num {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.stat-num small {
  font-size: 10px;
  font-weight: 500;
  color: #64748b;
  margin-left: 1px;
}

.stat-status {
  font-size: 12px;
  font-weight: 700;
}

.stat-status.success {
  color: #16a34a;
}

.stat-status.failed {
  color: #dc2626;
}

.stat-lbl {
  font-size: 10.5px;
  color: #94a3b8;
}

.stat-divider {
  width: 1px;
  height: 24px;
  background: #e2e8f0;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.empty-title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 4px;
}

.empty-desc {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.4;
}

.events-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.event-item {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  font-size: 12px;
  transition: border-color 0.15s ease;
}

.event-item:hover {
  border-color: #cbd5e1;
}

.event-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  cursor: pointer;
  user-select: none;
  background: #ffffff;
}

.event-left {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
}

.event-order {
  font-family: monospace;
  font-size: 11px;
  color: #94a3b8;
  width: 22px;
}

.phase-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 4px;
  flex-shrink: 0;
}

.phase-http { background: #f1f5f9; color: #475569; }
.phase-intent { background: #e0e7ff; color: #4338ca; }
.phase-plan { background: #dbeafe; color: #1d4ed8; }
.phase-order { background: #dcfce7; color: #15803d; }
.phase-memory { background: #f3e8ff; color: #7e22ce; }
.phase-default { background: #f1f5f9; color: #64748b; }

.event-type {
  font-family: monospace;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.latency-text {
  font-size: 10.5px;
  font-family: monospace;
  color: #94a3b8;
}

.expand-arrow {
  font-size: 12px;
  color: #94a3b8;
  transition: transform 0.2s ease;
}

.expand-arrow.rotated {
  transform: rotate(90deg);
}

.event-body {
  padding: 8px 10px;
  background: #f8fafc;
  border-top: 1px solid #f1f5f9;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
}

.body-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.body-lbl {
  font-weight: 600;
  color: #64748b;
}

.body-val {
  color: #1e293b;
}

.body-json {
  font-family: monospace;
  font-size: 10.5px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px;
  margin: 2px 0 0 0;
  max-height: 120px;
  overflow-y: auto;
  color: #334155;
  white-space: pre-wrap;
}

.error-row {
  background: #fee2e2;
  padding: 4px 6px;
  border-radius: 4px;
}

.error-text {
  color: #b91c1c;
  font-weight: 500;
}

.actions-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
  padding-top: 4px;
}

.full-btn {
  width: 100%;
  border-radius: 8px;
  font-size: 12px;
  height: 34px;
}

.sub-btn {
  color: #475569;
}
</style>
