<template>
  <div class="distill-viewer-container">
    <!-- Action Header -->
    <div class="distill-header">
      <div class="header-left">
        <div class="title-row">
          <el-icon><Compass /></el-icon>
          <span class="title-text">L3 长期偏好反思与蒸馏透视 (Offline Distillation)</span>
        </div>
        <p class="subtitle-text">
          由后台双主体蒸馏引擎对操作者决策行为（User L2）与乘车人行程经历（Passenger L2）进行周期性提炼与反思，生成分化长期记忆。
        </p>
      </div>

      <el-button
        type="primary"
        :loading="memoryStore.isDistilling"
        @click="handleTriggerDistill"
      >
        <el-icon><Refresh /></el-icon>
        手动触发双主体蒸馏
      </el-button>
    </div>

    <!-- L3 Dual-Scope Structured Overview Cards -->
    <div class="l3-scope-grid">
      <!-- Card 1: User L3 -->
      <div class="scope-card user-scope-card">
        <div class="scope-card-header">
          <div class="scope-title">
            <span class="scope-icon">👤</span>
            <span class="scope-name">用户决策偏好 (User L3)</span>
          </div>
          <span class="scope-badge user">操作者决策习惯</span>
        </div>
        <div class="scope-card-body">
          <div class="metric-row">
            <span class="metric-label">价格敏感度 (price_sensitivity)</span>
            <span class="metric-badge" :class="priceSensitivityLevel">
              {{ priceSensitivityLabel }}
            </span>
          </div>
          <div class="metric-row">
            <span class="metric-label">降价监控提醒阈值 (price_drop_ratio)</span>
            <span class="metric-text">{{ formatPriceDropRatio }}</span>
          </div>
          <div class="metric-row">
            <span class="metric-label">净节省生效门槛 (saving_threshold)</span>
            <span class="metric-text">{{ formatSavingThreshold }}</span>
          </div>
          <div class="scope-summary-tip">
            💡 提炼自使用者对降价推送、推荐采纳与改签退款等 User L2 行为事件的长期响应规律。
          </div>
        </div>
      </div>

      <!-- Card 2: Passenger L3 -->
      <div class="scope-card passenger-scope-card">
        <div class="scope-card-header">
          <div class="scope-title">
            <span class="scope-icon">🚄</span>
            <span class="scope-name">乘车人出行习惯 (Passenger L3)</span>
          </div>
          <span class="scope-badge passenger">各乘车人专属偏好</span>
        </div>
        <div class="scope-card-body">
          <div v-if="passengersL3.length === 0" class="empty-passenger-l3">
            暂无已沉淀的乘车人偏好（多次出行后自动蒸馏学习）
          </div>
          <div v-else class="passenger-l3-list">
            <div
              v-for="p in passengersL3"
              :key="p.passengerId"
              class="passenger-l3-item"
            >
              <div class="p-header">
                <span class="p-name">{{ p.name }}</span>
                <el-tag size="small" :type="p.isSelf ? 'primary' : 'success'" effect="light">
                  {{ p.isSelf ? '本人 (Passenger 0)' : '同行人' }}
                </el-tag>
              </div>
              <div class="p-prefs-chips">
                <div v-if="p.prefs.transport" class="p-chip">
                  <span class="chip-lbl">交通:</span>
                  <span class="chip-val">{{ formatTransport(p.prefs.transport) }}</span>
                  <span v-if="getConfidence(p.prefs.transport)" class="chip-conf">
                    {{ getConfidence(p.prefs.transport) }}%
                  </span>
                </div>
                <div v-if="p.prefs.time_window" class="p-chip">
                  <span class="chip-lbl">时段:</span>
                  <span class="chip-val">{{ formatTimeWindow(p.prefs.time_window) }}</span>
                  <span v-if="getConfidence(p.prefs.time_window)" class="chip-conf">
                    {{ getConfidence(p.prefs.time_window) }}%
                  </span>
                </div>
                <div v-if="p.prefs.seat" class="p-chip">
                  <span class="chip-lbl">座席:</span>
                  <span class="chip-val">{{ formatSeat(p.prefs.seat) }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="scope-summary-tip">
            🚄 提炼自各乘车人在实际订单与行程经历（Passenger L2）中的高频出行习惯。
          </div>
        </div>
      </div>
    </div>

    <!-- Distill Report Body -->
    <div class="report-card">
      <div class="report-meta-bar">
        <span class="meta-tag">报告文件: memory/distill/user_{{ memoryStore.distillReport?.userId || 1 }}.md</span>
        <span class="meta-status">双主体分化已就绪</span>
      </div>

      <div class="report-content">
        <div
          v-if="!memoryStore.distillReport?.content"
          class="empty-report"
        >
          暂无偏好蒸馏记录，点击右上角按钮即可立即触发生成喵~
        </div>

        <div v-else class="markdown-body">
          <div
            v-for="(para, idx) in formattedParagraphs"
            :key="idx"
            class="md-block"
          >
            <h1 v-if="para.type === 'h1'" class="md-h1">{{ para.text }}</h1>
            <h2 v-else-if="para.type === 'h2'" class="md-h2">{{ para.text }}</h2>
            <h3 v-else-if="para.type === 'h3'" class="md-h3">{{ para.text }}</h3>
            <ul v-else-if="para.type === 'list'" class="md-ul">
              <li v-for="(item, itemIdx) in para.items" :key="itemIdx">{{ item }}</li>
            </ul>
            <p v-else class="md-p">{{ para.text }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useMemoryStore } from '@/stores/memory'

const memoryStore = useMemoryStore()

const preferencesV2 = computed(() => {
  return memoryStore.distillReport?.preferencesV2 || memoryStore.profile?.preferences_v2 || {}
})

const userL3 = computed(() => {
  return preferencesV2.value.user || {}
})

const priceSensitivityLevel = computed(() => {
  const val = String(userL3.value.price_sensitivity?.value || userL3.value.price_sensitivity || '').toLowerCase()
  if (val === 'high') return 'badge-high'
  if (val === 'low') return 'badge-low'
  return 'badge-med'
})

const priceSensitivityLabel = computed(() => {
  const val = String(userL3.value.price_sensitivity?.value || userL3.value.price_sensitivity || '').toLowerCase()
  if (val === 'high') return '高敏感 (差价敏感/极低价优先)'
  if (val === 'low') return '低敏感 (体验至上/对差价不敏感)'
  if (val === 'medium') return '标准中等 (兼顾价格与耗时)'
  return '标准中等 (默认)'
})

const formatPriceDropRatio = computed(() => {
  const r = userL3.value.price_drop_ratio
  const val = r?.value !== undefined ? r.value : r
  if (val !== undefined && val !== null && val !== '') {
    return `${Math.round(Number(val) * 100)}%`
  }
  return '10% (标准模式)'
})

const formatSavingThreshold = computed(() => {
  const s = userL3.value.saving_threshold_yuan
  const val = s?.value !== undefined ? s.value : s
  if (val) return `¥${val}`
  return '¥50'
})

const passengersL3 = computed(() => {
  const pMap = preferencesV2.value.passengers || {}
  const roster = memoryStore.profile?.passengers || []
  const nameMap: Record<string, { name: string; isSelf: boolean }> = {}
  for (const p of roster) {
    const isSelf = String(p.passenger_id) === '0' || p.role === 'self'
    nameMap[String(p.passenger_id)] = {
      name: p.name || (isSelf ? '本人' : p.passenger_id),
      isSelf,
    }
  }

  return Object.entries(pMap).map(([pid, prefs]: [string, any]) => {
    const info = nameMap[pid] || { name: pid === '0' ? '本人' : `乘客 ${pid}`, isSelf: pid === '0' }
    return {
      passengerId: pid,
      name: info.name,
      isSelf: info.isSelf,
      prefs: prefs || {},
    }
  })
})

function formatTransport(entry: any): string {
  const v = String(entry?.value || entry || '').toLowerCase()
  if (v.includes('train')) return '高铁 / 火车'
  if (v.includes('flight')) return '民航飞机'
  if (v.includes('bus')) return '客运大巴'
  return v || '高铁'
}

function formatTimeWindow(entry: any): string {
  const v = String(entry?.value || entry || '').toLowerCase()
  if (v.includes('morning')) return '早间出发 (05:00-09:00)'
  if (v.includes('afternoon')) return '午后出发 (12:00-17:00)'
  if (v.includes('night')) return '夜间出发'
  return v || '早班'
}

function formatSeat(entry: any): string {
  const v = String(entry?.value || entry || '').toLowerCase()
  if (v.includes('window')) return '靠窗座'
  if (v.includes('aisle')) return '过道座'
  return entry?.value || entry || '二等座'
}

function getConfidence(entry: any): number | null {
  if (entry && typeof entry === 'object' && entry.confidence !== undefined) {
    return Math.round(Number(entry.confidence) * 100)
  }
  return null
}

async function handleTriggerDistill() {
  try {
    await memoryStore.triggerDistill()
    ElMessage.success('L3 偏好蒸馏执行完成，报告已刷新！')
  } catch (err: any) {
    ElMessage.error(err?.message || '蒸馏失败')
  }
}

interface MarkdownBlock {
  type: 'h1' | 'h2' | 'h3' | 'p' | 'list'
  text?: string
  items?: string[]
}

const formattedParagraphs = computed<MarkdownBlock[]>(() => {
  const raw = memoryStore.distillReport?.content || ''
  if (!raw) return []

  const lines = raw.split('\n')
  const blocks: MarkdownBlock[] = []
  let currentList: string[] = []

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      continue
    }

    if (trimmed.startsWith('# ')) {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      blocks.push({ type: 'h1', text: trimmed.replace(/^#\s+/, '') })
    } else if (trimmed.startsWith('## ')) {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      blocks.push({ type: 'h2', text: trimmed.replace(/^##\s+/, '') })
    } else if (trimmed.startsWith('### ')) {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      blocks.push({ type: 'h3', text: trimmed.replace(/^###\s+/, '') })
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      currentList.push(trimmed.replace(/^[-*]\s+/, ''))
    } else {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      blocks.push({ type: 'p', text: trimmed })
    }
  }

  if (currentList.length > 0) {
    blocks.push({ type: 'list', items: [...currentList] })
  }

  return blocks
})
</script>

<style scoped>
.distill-viewer-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.distill-header {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.l3-scope-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 768px) {
  .l3-scope-grid {
    grid-template-columns: 1fr;
  }
}

.scope-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
}

.scope-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.scope-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.scope-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 600;
}

.scope-badge.user {
  background: #f3e8ff;
  color: #7e22ce;
  border: 1px solid #e9d5ff;
}

.scope-badge.passenger {
  background: #dbeafe;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
}

.scope-card-body {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.metric-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #f1f5f9;
}

.metric-label {
  color: #64748b;
  font-weight: 500;
}

.metric-text {
  color: #1e293b;
  font-weight: 600;
}

.metric-badge {
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.metric-badge.badge-high {
  background: #fee2e2;
  color: #dc2626;
  border: 1px solid #fca5a5;
}

.metric-badge.badge-low {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.metric-badge.badge-med {
  background: #eff6ff;
  color: #2563eb;
  border: 1px solid #bfdbfe;
}

.scope-summary-tip {
  font-size: 11.5px;
  color: #94a3b8;
  line-height: 1.45;
  margin-top: auto;
  padding-top: 4px;
}

.empty-passenger-l3 {
  font-size: 12.5px;
  color: #94a3b8;
  padding: 20px 0;
  text-align: center;
}

.passenger-l3-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.passenger-l3-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.p-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.p-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.p-prefs-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.p-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11.5px;
}

.chip-lbl {
  color: #94a3b8;
}

.chip-val {
  font-weight: 600;
  color: #1e293b;
}

.chip-conf {
  background: #dcfce7;
  color: #15803d;
  padding: 0 4px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 700;
}

.report-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);
}

.report-meta-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  padding: 8px 16px;
  font-size: 11.5px;
}

.meta-tag {
  font-family: monospace;
  color: #475569;
}

.meta-status {
  background: #dcfce7;
  color: #15803d;
  padding: 1px 8px;
  border-radius: 9999px;
  font-weight: 600;
}

.report-content {
  padding: 24px;
  min-height: 300px;
}

.empty-report {
  text-align: center;
  color: #94a3b8;
  padding: 60px 0;
  font-size: 13px;
}

.markdown-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  line-height: 1.6;
  color: #1e293b;
}

.md-h1 {
  font-size: 20px;
  font-weight: 800;
  color: #0f172a;
  border-bottom: 2px solid #e2e8f0;
  padding-bottom: 8px;
  margin: 0 0 4px 0;
}

.md-h2 {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin: 12px 0 2px 0;
}

.md-h3 {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin: 8px 0 2px 0;
}

.md-p {
  font-size: 13px;
  margin: 0;
  color: #334155;
}

.md-ul {
  margin: 4px 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #334155;
}
</style>
