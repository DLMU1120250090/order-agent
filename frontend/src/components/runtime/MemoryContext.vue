<template>
  <div class="memory-context-panel">
    <!-- Header Banner -->
    <div class="memory-banner">
      <div class="banner-title">
        <el-icon><Collection /></el-icon>
        <span>本轮生效偏好记忆切片</span>
      </div>
      <p class="banner-desc">
        展示 Agent 在解析意图与打分规划时，从 L1-L3 检索并注入的个性化偏好特征及打分影响。
      </p>
    </div>

    <!-- Empty State -->
    <div v-if="runtimeStore.memoryItems.length === 0" class="empty-state">
      <div class="empty-icon">🧠</div>
      <div class="empty-title">暂无生效偏好上下文</div>
      <div class="empty-desc">发起对话后，此处将实时展示从记忆库唤醒的决策规则喵~</div>
    </div>

    <!-- Memory Injected Items List -->
    <div v-else class="memory-list">
      <div
        v-for="item in runtimeStore.memoryItems"
        :key="item.id"
        class="memory-card"
      >
        <div class="card-top">
          <div class="source-tag" :class="item.source.toLowerCase()">
            {{ sourceLabel(item.source) }}
          </div>
          <div v-if="item.confidence" class="confidence-badge">
            置信度 {{ Math.round(item.confidence * 100) }}%
          </div>
        </div>

        <div class="item-kv">
          <span class="item-key">{{ formatKey(item.key) }}</span>
          <span class="item-equal">:</span>
          <span class="item-value">{{ formatValue(item.value) }}</span>
        </div>

        <div v-if="item.description" class="item-desc">
          {{ formatDescription(item.description) }}
        </div>

        <div v-if="item.scoreImpact" class="score-impact">
          <span class="impact-label">策略加权:</span>
          <span class="impact-value">{{ item.scoreImpact }}</span>
        </div>
      </div>
    </div>

    <!-- Jump to Memory Center -->
    <div class="footer-actions">
      <router-link to="/travel/memory" class="jump-link">
        <el-button type="primary" plain class="full-btn">
          <el-icon><FolderOpened /></el-icon>
          前往 Memory Center 维护全局记忆
        </el-button>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRuntimeStore, type InjectedMemoryItem } from '@/stores/runtime'

const runtimeStore = useRuntimeStore()

function sourceLabel(source: InjectedMemoryItem['source']): string {
  switch (source) {
    case 'L1_PROFILE':
      return 'L1 静态画像'
    case 'L2_TRIP':
      return 'L2 历史行程'
    case 'L3_DISTILL':
      return 'L3 偏好蒸馏'
    default:
      return '系统规则'
  }
}

function formatKey(k: string): string {
  if (!k) return '偏好项'
  return k
}

function formatValue(v: any): string {
  if (!v) return ''
  const str = String(v).trim()
  if (str.startsWith('{') || str.startsWith('[')) {
    try {
      const obj = JSON.parse(str)
      if (obj && typeof obj === 'object') {
        const val = obj.value ?? obj.name ?? obj.detail
        if (val !== undefined) {
          return formatFriendlyValue(val)
        }
      }
    } catch {}
  }
  return formatFriendlyValue(str)
}

function formatFriendlyValue(val: any): string {
  const s = String(val).toLowerCase()
  if (s === 'economy' || s === '经济型') return '经济优先 (economy)'
  if (s === 'standard' || s === 'comfort' || s === '舒适型') return '标准舒适 (standard)'
  if (s === 'luxury' || s === 'premium' || s === '高端型') return '尊享商务 (luxury)'
  if (s.includes('train') || s.includes('高铁') || s.includes('火车')) return '高铁 / 火车 (train)'
  if (s.includes('flight') || s.includes('飞机')) return '民航飞机 (flight)'
  if (s.includes('window')) return '靠窗座 (window)'
  if (s.includes('aisle')) return '过道座 (aisle)'
  return String(val)
}

function formatDescription(desc: string): string {
  if (!desc) return ''
  if (desc.includes('{') && desc.includes('}')) {
    try {
      const match = desc.match(/\[([^=]+)=(.+)\]/)
      if (match) {
        const k = match[1]
        const rawJson = match[2]
        const parsed = JSON.parse(rawJson)
        const v = parsed?.value ?? parsed
        return `从画像与记忆中自动补全槽位 [${k}: ${formatFriendlyValue(v)}]`
      }
    } catch {
      return desc.replace(/\{.*?\}/g, '').replace(/\[.*?\=.*?\]/g, '已结合记忆自动补全')
    }
  }
  return desc
}
</script>

<style scoped>
.memory-context-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

.memory-banner {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
}

.banner-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 4px;
}

.banner-desc {
  font-size: 11.5px;
  color: #64748b;
  line-height: 1.45;
  margin: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px 16px;
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
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.memory-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  transition: all 0.2s ease;
  overflow: hidden;
  max-width: 100%;
  box-sizing: border-box;
}

.memory-card:hover {
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.source-tag {
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
}

.source-tag.l1_profile {
  background: #e0f2fe;
  color: #0369a1;
}

.source-tag.l2_trip {
  background: #dcfce7;
  color: #15803d;
}

.source-tag.l3_distill {
  background: #f3e8ff;
  color: #7e22ce;
}

.source-tag.system {
  background: #f1f5f9;
  color: #475569;
}

.confidence-badge {
  font-size: 10.5px;
  font-family: monospace;
  color: #64748b;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 1px 5px;
  border-radius: 4px;
}

.item-kv {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12.5px;
  margin-bottom: 4px;
  flex-wrap: wrap;
  word-break: break-all;
  overflow-wrap: anywhere;
}

.item-key {
  color: #0f172a;
  font-weight: 700;
  font-size: 12.5px;
  word-break: break-all;
}

.item-equal {
  color: #94a3b8;
  font-weight: 600;
}

.item-value {
  color: #2563eb;
  font-weight: 600;
  font-size: 12.5px;
  word-break: break-all;
  overflow-wrap: anywhere;
}

.item-desc {
  font-size: 11.5px;
  color: #64748b;
  line-height: 1.45;
  margin-bottom: 6px;
  word-break: break-all;
  overflow-wrap: anywhere;
}

.score-impact {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  padding: 3px 8px;
  border-radius: 6px;
  width: fit-content;
}

.impact-label {
  font-weight: 500;
}

.impact-value {
  font-weight: 700;
}

.footer-actions {
  margin-top: 8px;
}

.jump-link {
  text-decoration: none;
  display: block;
}

.full-btn {
  width: 100%;
  border-radius: 8px;
  font-size: 12px;
}
</style>
