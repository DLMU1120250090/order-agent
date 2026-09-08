<template>
  <div class="user-event-card">
    <div class="event-left">
      <div class="event-icon-badge" :style="{ backgroundColor: eventMeta.bgColor, color: eventMeta.color }">
        <span>{{ eventMeta.icon }}</span>
      </div>
      <div class="event-info">
        <div class="event-title-row">
          <span class="event-name">{{ eventMeta.label }}</span>
          <span class="event-type-code">{{ event.eventType }}</span>
          <el-tag v-if="event.orderNo" size="small" type="info" effect="plain" class="order-tag">
            单号: {{ event.orderNo }}
          </el-tag>
        </div>
        <div class="event-context">
          <span v-if="eventMeta.summary" class="context-summary">{{ eventMeta.summary }}</span>
          <span v-else-if="hasContextDetails" class="context-details">{{ formatContext(event.context) }}</span>
          <span v-else class="context-empty">无附加参数</span>
        </div>
      </div>
    </div>

    <div class="event-right">
      <span class="event-time">{{ formatTime(event.createdAt) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { UserMemoryEvent } from '@/types/memory'

const props = defineProps<{
  event: UserMemoryEvent
}>()

interface EventMeta {
  label: string
  icon: string
  color: string
  bgColor: string
  summary?: string
}

const eventMeta = computed<EventMeta>(() => {
  const t = props.event.eventType
  const ctx = props.event.context || {}

  switch (t) {
    case 'price_drop_accepted':
      return {
        label: '降价监控 - 采纳降价推送',
        icon: '💰',
        color: '#16a34a',
        bgColor: '#dcfce7',
        summary: ctx.saving ? `节省金额: ¥${ctx.saving}` : '已根据降价提醒执行改签或重订',
      }
    case 'price_drop_ignored':
      return {
        label: '降价监控 - 忽略差价推送',
        icon: '📉',
        color: '#64748b',
        bgColor: '#f1f5f9',
        summary: '差价未达到用户预期或暂不需要变更',
      }
    case 'recommend_accepted':
      return {
        label: '方案推荐 - 采纳推荐方案',
        icon: '👍',
        color: '#2563eb',
        bgColor: '#dbeafe',
        summary: ctx.reason ? `推荐理由: ${ctx.reason}` : `采纳方案 #${ctx.planId || ''}`,
      }
    case 'recommend_rejected':
      return {
        label: '方案推荐 - 换一批 / 拒绝',
        icon: '🔄',
        color: '#d97706',
        bgColor: '#fef3c7',
        summary: ctx.reason ? `拒绝原因: ${ctx.reason}` : '触发换一批，探索更多偏好',
      }
    case 'change_confirmed':
      return {
        label: '改签处理 - 确认改签',
        icon: '🎫',
        color: '#0284c7',
        bgColor: '#e0f2fe',
        summary: ctx.target_train ? `改签至: ${ctx.target_train}` : '用户确认改签新行程',
      }
    case 'change_rejected':
      return {
        label: '改签处理 - 放弃改签',
        icon: '🚫',
        color: '#94a3b8',
        bgColor: '#f8fafc',
        summary: '用户放弃改签，保留原行程',
      }
    case 'refund_confirmed':
      return {
        label: '退票处理 - 确认退票',
        icon: '↩️',
        color: '#dc2626',
        bgColor: '#fee2e2',
        summary: '已确认退票并退款',
      }
    case 'monitor_toggled':
      return {
        label: '监控开关 - 状态变更',
        icon: '🔔',
        color: '#9333ea',
        bgColor: '#f3e8ff',
        summary: ctx.enabled ? '已开启自动降价监控' : '已关闭降价监控',
      }
    case 'reminder_set':
      return {
        label: '出行提醒 - 设置提醒',
        icon: '⏰',
        color: '#eab308',
        bgColor: '#fef9c3',
        summary: ctx.hours ? `提前 ${ctx.hours} 小时通知` : '设置发车提醒',
      }
    default:
      return {
        label: '决策行为记录',
        icon: '📌',
        color: '#475569',
        bgColor: '#f1f5f9',
      }
  }
})

const hasContextDetails = computed(() => {
  return props.event.context && Object.keys(props.event.context).length > 0
})

function formatContext(ctx?: Record<string, any>): string {
  if (!ctx) return ''
  return Object.entries(ctx)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' | ')
}

function formatTime(isoStr?: string): string {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    return d.toLocaleString()
  } catch {
    return isoStr
  }
}
</script>

<style scoped>
.user-event-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}

.user-event-card:hover {
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.event-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.event-icon-badge {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.event-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.event-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.event-name {
  font-size: 13.5px;
  font-weight: 700;
  color: #1e293b;
}

.event-type-code {
  font-family: monospace;
  font-size: 11px;
  color: #94a3b8;
  background: #f8fafc;
  padding: 1px 5px;
  border-radius: 4px;
}

.order-tag {
  font-family: monospace;
  font-size: 11px;
}

.event-context {
  font-size: 12px;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-summary {
  color: #334155;
  font-weight: 500;
}

.context-details {
  color: #64748b;
}

.context-empty {
  color: #cbd5e1;
  font-style: italic;
}

.event-right {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.event-time {
  font-size: 11.5px;
  color: #94a3b8;
  white-space: nowrap;
}
</style>
