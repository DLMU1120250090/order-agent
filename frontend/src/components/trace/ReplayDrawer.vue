<template>
  <el-drawer
    v-model="traceStore.showReplayDrawer"
    title="离线 Replay 决策比对验证 (Dry-run)"
    size="720px"
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
        <span>正在调用底层规划规则层执行 Dry-run 重新计算...</span>
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

        <!-- 3 Layers Comparison Tabs/Cards -->
        <div class="layers-container">
          <!-- Layer 1: Clarify Rules -->
          <div class="layer-card">
            <div class="layer-header">
              <div class="layer-title">
                <span class="layer-badge">Layer 1</span>
                <span>澄清判定规则层 (Clarify Rules)</span>
              </div>
              <span
                class="diff-badge"
                :class="hasDiff('clarify') ? 'has-diff' : 'identical'"
              >
                {{ hasDiff('clarify') ? '存在决策差异' : '结果一致' }}
              </span>
            </div>

            <div class="compare-grid">
              <div class="compare-col before-col">
                <div class="col-title">Before (原生产决策)</div>
                <pre class="col-json">{{ formatJson(traceStore.replayResult.layers?.clarify?.before) }}</pre>
              </div>
              <div class="compare-col after-col">
                <div class="col-title">After (Dry-run 重算)</div>
                <pre class="col-json">{{ formatJson(traceStore.replayResult.layers?.clarify?.after) }}</pre>
              </div>
            </div>
          </div>

          <!-- Layer 2: Planner Rules -->
          <div class="layer-card">
            <div class="layer-header">
              <div class="layer-title">
                <span class="layer-badge">Layer 2</span>
                <span>多目标规划规则层 (Planner Rules)</span>
              </div>
              <span
                class="diff-badge"
                :class="hasDiff('planner') ? 'has-diff' : 'identical'"
              >
                {{ hasDiff('planner') ? '存在决策差异' : '结果一致' }}
              </span>
            </div>

            <div class="compare-grid">
              <div class="compare-col before-col">
                <div class="col-title">Before (原生产决策)</div>
                <pre class="col-json">{{ formatJson(traceStore.replayResult.layers?.planner?.before) }}</pre>
              </div>
              <div class="compare-col after-col">
                <div class="col-title">After (Dry-run 重算)</div>
                <pre class="col-json">{{ formatJson(traceStore.replayResult.layers?.planner?.after) }}</pre>
              </div>
            </div>
          </div>

          <!-- Layer 3: Change/Refund Rules -->
          <div class="layer-card">
            <div class="layer-header">
              <div class="layer-title">
                <span class="layer-badge">Layer 3</span>
                <span>改签退票决策服务 (Change / Refund)</span>
              </div>
              <span
                class="diff-badge"
                :class="hasDiff('change') ? 'has-diff' : 'identical'"
              >
                {{ hasDiff('change') ? '存在决策差异' : '结果一致' }}
              </span>
            </div>

            <div class="compare-grid">
              <div class="compare-col before-col">
                <div class="col-title">Before (原生产决策)</div>
                <pre class="col-json">{{ formatJson(traceStore.replayResult.layers?.change?.before) }}</pre>
              </div>
              <div class="compare-col after-col">
                <div class="col-title">After (Dry-run 重算)</div>
                <pre class="col-json">{{ formatJson(traceStore.replayResult.layers?.change?.after) }}</pre>
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
import { useTraceStore } from '@/stores/trace'
import { ElMessage } from 'element-plus'

const traceStore = useTraceStore()

async function handleReplay() {
  try {
    await traceStore.runReplay()
    ElMessage.success('离线 Replay 执行完毕')
  } catch (err: any) {
    ElMessage.error(err?.message || 'Replay 失败')
  }
}

function hasDiff(layerKey: string): boolean {
  if (!traceStore.replayResult?.diff) return false
  const d = traceStore.replayResult.diff[layerKey]
  return d && Object.keys(d).length > 0
}

function formatJson(data: any): string {
  if (!data) return '(无数据 / skipped)'
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleTimeString()
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
  gap: 14px;
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
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.layer-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.layer-badge {
  font-size: 10.5px;
  background: #0284c7;
  color: #ffffff;
  padding: 1px 6px;
  border-radius: 4px;
}

.diff-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 9999px;
}

.diff-badge.identical {
  background: #dcfce7;
  color: #166534;
}

.diff-badge.has-diff {
  background: #fee2e2;
  color: #991b1b;
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
}

.col-title {
  font-size: 11.5px;
  font-weight: 600;
  color: #475569;
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

.replay-empty {
  padding: 40px 0;
}
</style>
