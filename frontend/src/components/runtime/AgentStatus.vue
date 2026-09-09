<template>
  <div class="agent-status-panel">
    <!-- Task Overview Card -->
    <div class="task-card">
      <div class="task-card-header">
        <span class="task-label">当前调度任务</span>
        <span
          class="status-pill"
          :class="overallStatusClass"
        >
          <span class="pill-dot"></span>
          {{ overallStatusText }}
        </span>
      </div>
      <div class="task-title">{{ runtimeStore.currentTask }}</div>
      <div class="task-meta">
        <span class="meta-item">
          <el-icon><User /></el-icon>
          <span>活跃智能体: <strong>{{ runtimeStore.activeAgent }}</strong></span>
        </span>
        <span class="meta-item">
          <el-icon><Timer /></el-icon>
          <span>端到端耗时: <strong>{{ runtimeStore.totalLatencyMs }} ms</strong></span>
        </span>
      </div>
    </div>

    <!-- Pipeline Stages Sequence -->
    <div class="pipeline-section">
      <div class="pipeline-section-title">
        <span>执行链路流转 (Agent Pipeline)</span>
        <span class="step-count">4 阶段</span>
      </div>

      <div class="stages-timeline">
        <div
          v-for="(stage, index) in runtimeStore.pipelineStages"
          :key="stage.id"
          class="stage-node"
          :class="[`status-${stage.status.toLowerCase()}`, { active: stage.status === 'RUNNING' }]"
        >
          <!-- Left Step Indicator & Line -->
          <div class="stage-indicator">
            <div class="node-icon">
              <el-icon v-if="stage.status === 'SUCCESS'"><Check /></el-icon>
              <el-icon v-else-if="stage.status === 'RUNNING'" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="stage.status === 'FAILED'"><Close /></el-icon>
              <el-icon v-else-if="stage.status === 'SKIPPED'"><Minus /></el-icon>
              <span v-else class="step-num">{{ index + 1 }}</span>
            </div>
            <div v-if="index < runtimeStore.pipelineStages.length - 1" class="connector-line"></div>
          </div>

          <!-- Stage Details Card -->
          <div class="stage-card">
            <div class="stage-header">
              <div class="stage-name-box">
                <span class="stage-name">{{ stage.name }}</span>
                <span class="stage-role">{{ stage.role }}</span>
              </div>
              <div class="stage-metrics">
                <span v-if="stage.latencyMs > 0" class="latency-badge">
                  {{ stage.latencyMs }} ms
                </span>
                <span class="status-tag" :class="[stage.status.toLowerCase(), { waiting: stage.id === 'stage-3' && isClarifying }]">
                  {{ stageStatusLabel(stage.status, stage.id) }}
                </span>
              </div>
            </div>

            <div class="stage-body">
              <p class="stage-summary">{{ stage.summary }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRuntimeStore, type PipelineStage } from '@/stores/runtime'

const runtimeStore = useRuntimeStore()

function parsePayload(val: any): any {
  if (!val) return null
  if (typeof val === 'object') return val
  if (typeof val === 'string') {
    try {
      return JSON.parse(val)
    } catch {
      return val
    }
  }
  return val
}

const isClarifying = computed(() => {
  const evs = runtimeStore.events
  const clarifyEv = evs.find(e => e.eventType === 'CLARIFY_DECISION')
  if (clarifyEv) {
    const out = parsePayload(clarifyEv.outputPayload) || clarifyEv.decision || {}
    if (out.action === 'ASK') return true
  }
  const respReady = evs.find(e => e.eventType === 'RESPONSE_READY')
  if (respReady && (respReady.phase === 'CLARIFY' || respReady.phase === 'MEMORY_CONFIRM')) {
    return true
  }
  return false
})

const overallStatusClass = computed(() => {
  if (!runtimeStore.traceDetail) return 'pending'
  const stages = runtimeStore.pipelineStages
  if (stages.some(s => s.status === 'FAILED')) return 'failed'
  if (runtimeStore.isOrderRefunded) return 'success'
  if (runtimeStore.isOrderChanged) return 'success'
  if (runtimeStore.isOrderPaid) return 'success'
  if (runtimeStore.isWaitingPayment) return 'waiting'
  if (stages.some(s => s.status === 'RUNNING')) return 'running'
  if (isClarifying.value) return 'waiting'
  const evs = runtimeStore.events
  if (evs.some(e => e.eventType === 'ORDER_QUERIED' || e.eventType === 'TRIP_QUERIED')) return 'success'
  if (stages.some(s => s.id === 'stage-3' && s.status === 'SUCCESS')) return 'success'
  if (stages.some(s => s.id === 'stage-4' && s.status === 'SUCCESS')) return 'success'
  return 'pending'
})

const overallStatusText = computed(() => {
  if (!runtimeStore.traceDetail) return '就绪待命'
  const stages = runtimeStore.pipelineStages
  if (stages.some(s => s.status === 'FAILED')) return '执行异常'
  if (runtimeStore.isOrderRefunded) return '退款完成'
  if (runtimeStore.isOrderChanged) return '改签完成'
  if (runtimeStore.isOrderPaid) return '出票完成'
  if (runtimeStore.isWaitingPayment) return '等待支付'
  if (stages.some(s => s.status === 'RUNNING')) return '规划流转中'
  if (isClarifying.value) return '等待用户确认'
  const evs = runtimeStore.events
  if (evs.some(e => e.eventType === 'ORDER_QUERIED')) return '查询完成'
  if (evs.some(e => e.eventType === 'TRIP_QUERIED')) return '行程已导出'
  if (stages.some(s => s.id === 'stage-3' && s.status === 'SUCCESS')) return '规划成功'
  if (stages.some(s => s.id === 'stage-4' && s.status === 'SUCCESS')) return '履约就绪'
  return '就绪待命'
})

function stageStatusLabel(status: PipelineStage['status'], stageId?: string): string {
  switch (status) {
    case 'SUCCESS':
      return '已完成'
    case 'RUNNING':
      return '执行中'
    case 'FAILED':
      return '失败'
    case 'SKIPPED':
      return '无需规划'
    case 'PENDING':
    default:
      if (stageId === 'stage-3' && isClarifying.value) return '待确认'
      return '待触发'
  }
}
</script>

<style scoped>
.agent-status-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

/* Task Overview Card */
.task-card {
  background: linear-gradient(135deg, #f0f7ff 0%, #e0f2fe 100%);
  border: 1px solid #bae6fd;
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 2px 6px rgba(14, 165, 233, 0.06);
}

.task-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.task-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: #0284c7;
  letter-spacing: 0.5px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 9999px;
}

.status-pill.success {
  background: #dcfce7;
  color: #166534;
}

.status-pill.running {
  background: #dbeafe;
  color: #1e40af;
}

.status-pill.failed {
  background: #fee2e2;
  color: #991b1b;
}

.status-pill.pending {
  background: #f1f5f9;
  color: #64748b;
}

.status-pill.waiting {
  background: #fef3c7;
  color: #b45309;
  border: 1px solid #fde68a;
}

.status-pill.waiting .pill-dot {
  background: #f59e0b;
  animation: pulse-dot 1.5s infinite;
}

.pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.status-pill.running .pill-dot {
  animation: pulse-dot 1.2s infinite;
}

@keyframes pulse-dot {
  0% { transform: scale(0.8); opacity: 0.5; }
  50% { transform: scale(1.3); opacity: 1; }
  100% { transform: scale(0.8); opacity: 0.5; }
}

.task-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
}

.task-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #475569;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.meta-item strong {
  color: #0369a1;
  font-weight: 600;
}

/* Pipeline Section */
.pipeline-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 12px;
}

.step-count {
  font-size: 11px;
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 4px;
  color: #475569;
}

.stages-timeline {
  display: flex;
  flex-direction: column;
}

.stage-node {
  display: flex;
  gap: 12px;
  position: relative;
}

.stage-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 26px;
  flex-shrink: 0;
}

.node-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.2s ease;
  z-index: 1;
}

.status-success .node-icon {
  background: #22c55e;
  color: #ffffff;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.15);
}

.status-running .node-icon {
  background: #3b82f6;
  color: #ffffff;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
}

.status-failed .node-icon {
  background: #ef4444;
  color: #ffffff;
}

.status-pending .node-icon {
  background: #e2e8f0;
  color: #94a3b8;
}

.status-skipped .node-icon {
  background: #f1f5f9;
  color: #64748b;
  border: 1.5px dashed #cbd5e1;
}

.step-num {
  font-size: 11px;
}

.connector-line {
  flex: 1;
  width: 2px;
  background: #e2e8f0;
  margin: 4px 0;
  min-height: 24px;
}

.status-success .connector-line,
.status-skipped .connector-line {
  background: #86efac;
}

.stage-card {
  flex: 1;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  transition: border-color 0.2s ease;
}

.stage-node.active .stage-card {
  border-color: #93c5fd;
  background: #fbfdff;
}

.stage-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.stage-name-box {
  display: flex;
  flex-direction: column;
}

.stage-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.stage-role {
  font-size: 11px;
  color: #64748b;
}

.stage-metrics {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.latency-badge {
  font-size: 10.5px;
  font-family: monospace;
  background: #f8fafc;
  color: #64748b;
  border: 1px solid #e2e8f0;
  padding: 1px 5px;
  border-radius: 4px;
}

.status-tag {
  font-size: 10.5px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
}

.status-tag.success {
  background: #dcfce7;
  color: #15803d;
}

.status-tag.running {
  background: #dbeafe;
  color: #1d4ed8;
}

.status-tag.failed {
  background: #fee2e2;
  color: #b91c1c;
}

.status-tag.skipped {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #cbd5e1;
}

.status-tag.pending {
  background: #f1f5f9;
  color: #94a3b8;
}

.status-tag.waiting {
  background: #fef3c7;
  color: #b45309;
  border: 1px solid #fde68a;
}

.stage-body {
  margin-top: 4px;
}

.stage-summary {
  font-size: 12px;
  color: #475569;
  line-height: 1.45;
  margin: 0;
}
</style>
