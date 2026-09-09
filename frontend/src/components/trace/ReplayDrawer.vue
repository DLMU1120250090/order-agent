<template>
  <el-drawer
    v-model="traceStore.showReplayDrawer"
    title="离线 Replay 决策比对验证 (Dry-run)"
    size="860px"
    direction="rtl"
    destroy-on-close
  >
    <div class="replay-drawer-content">
      <!-- Drawer Header Bar -->
      <div class="replay-bar">
        <div class="replay-meta">
          <span class="meta-label">重放 Trace:</span>
          <span class="meta-trace-id">{{ traceStore.selectedTraceId }}</span>
        </div>
        <el-button
          type="primary"
          :loading="traceStore.isReplaying"
          @click="handleReplay"
        >
          <el-icon><RefreshRight /></el-icon>
          重新运行 Replay
        </el-button>
      </div>

      <!-- Loading State -->
      <div v-if="traceStore.isReplaying" class="replay-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在调用底层规则引擎执行 Dry-run 决策重放与比对...</span>
      </div>

      <!-- Result View -->
      <div v-else-if="traceStore.replayResult" class="replay-results">
        <!-- Replay Notice Card -->
        <div class="notice-card">
          <el-icon><InfoFilled /></el-icon>
          <div class="notice-text">
            <span>{{ traceStore.replayResult.note }}</span>
            <small>重放时间: {{ formatDate(traceStore.replayResult.replayedAt) }}</small>
          </div>
        </div>

        <!-- 3 Layers Comparison Cards -->
        <div class="layers-container">
          <div
            v-for="cfg in LAYER_CONFIGS"
            :key="cfg.key"
            class="layer-card"
          >
            <!-- Layer Header -->
            <div class="layer-header">
              <div class="layer-title-box">
                <div class="layer-title">
                  <span class="layer-badge">{{ cfg.badge }}</span>
                  <span class="layer-name">{{ cfg.title }}</span>
                </div>
                <div class="layer-desc">{{ cfg.desc }}</div>
              </div>
              <span
                class="diff-badge"
                :class="getDiffStatus(cfg.key)"
              >
                {{
                  getDiffStatus(cfg.key) === 'skipped'
                    ? '⚪ 无需比对 (已跳过)'
                    : getDiffStatus(cfg.key) === 'diff'
                    ? '🔴 存在决策差异'
                    : '🟢 决策结果一致'
                }}
              </span>
            </div>

            <!-- Compare Grid -->
            <div class="compare-grid">
              <!-- Column Left: Before -->
              <div class="compare-col before-col">
                <div class="col-head-bar">
                  <span class="col-title">Before (原生产决策)</span>

                  <!-- 精准来源指示胶囊 -->
                  <div class="source-badge-wrap">
                    <button
                      v-if="getSource(cfg.key)?.hasEvent"
                      type="button"
                      class="source-pill has-event"
                      :title="`完整事件: ${getSource(cfg.key)?.eventType} | 点击在主时间轴高亮定位此节点`"
                      @click="handleLocateStep(getSource(cfg.key)?.stepOrder)"
                    >
                      <span class="pin-icon">📌</span>
                      <span class="src-text">节点 #{{ getSource(cfg.key)?.stepOrder }} · {{ formatEventType(getSource(cfg.key)?.eventType) }}</span>
                      <span class="jump-arrow">🎯 定位</span>
                    </button>
                    <span
                      v-else
                      class="source-pill no-event"
                      title="原 Trace 执行链路未经历此阶段决策节点"
                    >
                      ⚪ 未经历此阶段决策
                    </span>
                  </div>
                </div>

                <pre class="col-json">{{ formatJson(getLayerData(cfg.key)?.before) }}</pre>

                <!-- 来源操作栏：仅当有来源事件时展示展开原始报文 -->
                <div v-if="getSource(cfg.key)?.hasEvent" class="source-bottom-bar">
                  <button
                    type="button"
                    class="src-action-btn raw-btn"
                    @click="toggleRaw(cfg.key)"
                  >
                    <el-icon><Document /></el-icon>
                    {{ isRawOpen(cfg.key) ? '收起节点原始报文' : '展开节点原始报文' }}
                  </button>
                </div>

                <!-- 原始报文快速就地预览 -->
                <div v-if="getSource(cfg.key)?.hasEvent && isRawOpen(cfg.key)" class="raw-expand-panel">
                  <div class="raw-panel-header">
                    <span>节点 #{{ getSource(cfg.key)?.stepOrder }} ({{ getSource(cfg.key)?.eventType }}) 完整原始报文快照</span>
                  </div>
                  <pre class="raw-json-block">{{ formatJson(getSource(cfg.key)?.rawEvent) }}</pre>
                </div>

                <!-- 未经历阶段提示 -->
                <div v-if="!getSource(cfg.key)?.hasEvent" class="no-source-notice">
                  ℹ️ {{ getSource(cfg.key)?.summary || '原 Trace 执行流未进入该阶段，无需进行规则校验' }}
                </div>
              </div>

              <!-- Column Right: After -->
              <div class="compare-col after-col">
                <div class="col-head-bar">
                  <span class="col-title">After (Dry-run 重算)</span>
                  <span class="rule-calc-tag">规则引擎实时计算</span>
                </div>

                <pre class="col-json">{{ formatJson(getLayerData(cfg.key)?.after) }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else class="replay-empty">
        <el-empty description="点击上方按钮开始执行离线 Replay 比对" />
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useTraceStore } from '@/stores/trace'
import { ElMessage } from 'element-plus'
import {
  RefreshRight,
  InfoFilled,
  Loading,
  Document,
} from '@element-plus/icons-vue'
import { formatBeijingDateTime } from '@/utils/time'

const traceStore = useTraceStore()

const LAYER_CONFIGS = [
  {
    key: 'clarify',
    badge: 'Layer 1',
    title: '澄清判定规则层 (Clarify Rules)',
    desc: '检测关键槽位完整度，判定输出 ASK 反问澄清还是 READY 就绪',
  },
  {
    key: 'planner',
    badge: 'Layer 2',
    title: '多目标规划规则层 (Planner Rules)',
    desc: '多方案候选生成、组合权重打分与推荐排序（Dry-run 纯内存计算）',
  },
  {
    key: 'change',
    badge: 'Layer 3',
    title: '改签退票决策服务 (Change / Refund)',
    desc: '读取退改政策，评估改签手续费损失与最优退改替代方案',
  },
]

const openRawMap = ref<Record<string, boolean>>({})

function toggleRaw(layerKey: string) {
  openRawMap.value[layerKey] = !openRawMap.value[layerKey]
}

function isRawOpen(layerKey: string): boolean {
  return !!openRawMap.value[layerKey]
}

function getLayerData(layerKey: string) {
  return traceStore.replayResult?.layers?.[layerKey]
}

function getSource(layerKey: string) {
  return getLayerData(layerKey)?.source
}

function handleLocateStep(stepOrder?: number) {
  if (stepOrder === undefined || stepOrder === null) return
  traceStore.highlightStep(stepOrder)
  ElMessage.success(`已在底层时间轴定位并高亮节点 #${stepOrder}`)
}

async function handleReplay() {
  try {
    await traceStore.runReplay()
    ElMessage.success('离线 Replay 执行完毕')
  } catch (err: any) {
    ElMessage.error(err?.message || 'Replay 失败')
  }
}

function getDiffStatus(layerKey: string): 'skipped' | 'identical' | 'diff' {
  const layer = getLayerData(layerKey)
  if (!layer) return 'skipped'
  const bSkipped = layer.before && typeof layer.before === 'object' && 'skipped' in layer.before
  const aSkipped = layer.after && typeof layer.after === 'object' && 'skipped' in layer.after
  if (bSkipped && aSkipped) return 'skipped'
  const d = traceStore.replayResult?.diff?.[layerKey]
  if (!d) return 'identical'
  return d.identical ? 'identical' : 'diff'
}

function formatJson(data: any): string {
  if (!data) return '(无数据 / skipped)'
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function formatEventType(type?: string): string {
  if (!type) return ''
  const map: Record<string, string> = {
    CLARIFY_DECISION: '澄清判定',
    PLAN_RANKED: '方案比选',
    ORDER_CHANGE_DECISION: '退改决策',
  }
  return map[type] || type
}

function formatDate(dateStr?: string): string {
  return formatBeijingDateTime(dateStr)
}
</script>

<style scoped>
.replay-drawer-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
}

.replay-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.replay-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.meta-label {
  color: #64748b;
}

.meta-trace-id {
  font-family: monospace;
  font-weight: 700;
  color: #0f172a;
}

.replay-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 0;
  color: #2563eb;
  font-size: 14px;
}

.replay-loading .el-icon {
  font-size: 32px;
}

.replay-results {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
}

.notice-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 10px 14px;
  color: #1e40af;
  font-size: 12px;
}

.notice-card .el-icon {
  font-size: 16px;
  margin-top: 2px;
  flex-shrink: 0;
}

.notice-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.notice-text small {
  color: #60a5fa;
  font-size: 11px;
}

.layers-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.layer-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.layer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 12px;
}

.layer-title-box {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.layer-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 700;
  color: #0f172a;
}

.layer-badge {
  font-size: 10.5px;
  background: #0284c7;
  color: #ffffff;
  padding: 1px 6px;
  border-radius: 4px;
}

.layer-desc {
  font-size: 11.5px;
  color: #64748b;
}

.diff-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 9999px;
  white-space: nowrap;
}

.diff-badge.identical {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.diff-badge.has-diff {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.diff-badge.skipped {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.compare-col {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.col-head-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 28px;
}

.col-title {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  white-space: nowrap;
}

/* 来源指示胶囊 */
.source-badge-wrap {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.source-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  border-radius: 6px;
  padding: 2px 8px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  border: 1px solid transparent;
}

.source-pill.has-event {
  background: #ecfdf5;
  color: #047857;
  border-color: #a7f3d0;
  cursor: pointer;
  transition: all 0.15s ease;
}

.source-pill.has-event:hover {
  background: #d1fae5;
  border-color: #6ee7b7;
  transform: translateY(-1px);
}

.source-pill.has-event .jump-arrow {
  font-size: 10px;
  background: #10b981;
  color: #ffffff;
  padding: 1px 5px;
  border-radius: 4px;
  margin-left: 2px;
}

.source-pill.no-event {
  background: #f1f5f9;
  color: #64748b;
  border-color: #e2e8f0;
}

.rule-calc-tag {
  font-size: 11px;
  color: #2563eb;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
  white-space: nowrap;
}

.col-json {
  font-family: monospace;
  font-size: 11.5px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 10px;
  margin: 0;
  min-height: 120px;
  max-height: 240px;
  overflow-y: auto;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-all;
}

.before-col .col-json {
  border-left: 3px solid #94a3b8;
}

.after-col .col-json {
  border-left: 3px solid #3b82f6;
}

/* 来源底部操作栏 */
.source-bottom-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}

.src-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid #e2e8f0;
  transition: all 0.15s ease;
  background: #f8fafc;
  color: #475569;
  white-space: nowrap;
}

.src-action-btn:hover {
  background: #e2e8f0;
  color: #1e293b;
}

.raw-expand-panel {
  background: #f1f5f9;
  border: 1px dashed #cbd5e1;
  border-radius: 6px;
  padding: 8px 10px;
  margin-top: 4px;
}

.raw-panel-header {
  font-size: 11px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 4px;
}

.raw-json-block {
  font-family: monospace;
  font-size: 11px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 8px;
  margin: 0;
  max-height: 160px;
  overflow-y: auto;
  line-height: 1.35;
  white-space: pre-wrap;
  word-break: break-all;
}

.no-source-notice {
  font-size: 11px;
  color: #94a3b8;
  background: #f8fafc;
  border: 1px dashed #e2e8f0;
  border-radius: 6px;
  padding: 6px 10px;
  margin-top: 4px;
}

.replay-empty {
  padding: 40px 0;
}
</style>
