<template>
  <div class="message-row" :class="[message.role]">
    <!-- Avatar -->
    <div v-if="message.role !== 'system'" class="avatar-wrap">
      <div v-if="message.role === 'assistant'" class="avatar agent-avatar" title="出行助手 Agent">
        🐟
      </div>
      <div v-else class="avatar user-avatar" title="用户">
        👤
      </div>
    </div>

    <!-- Bubble Content -->
    <div class="message-body">
      <!-- Timestamp or Role Tag -->
      <div class="message-meta">
        <span class="meta-role">{{ roleLabel }}</span>
        <span class="meta-time">{{ message.timestamp }}</span>
        <span v-if="message.traceId" class="trace-tag" :title="'Trace ID: ' + message.traceId">
          Trace #{{ message.traceId.slice(-6) }}
        </span>
      </div>

      <!-- Main Text Box -->
      <div class="text-bubble">
        <div class="text-content" v-html="formattedText"></div>
      </div>

      <!-- Attached Cards -->
      <!-- 1. Clarification Card -->
      <ClarifyCard
        v-if="message.responseType === 'CLARIFY' || (message.missingSlots && message.missingSlots.length > 0) || (message.confirmFields && message.confirmFields.length > 0)"
        :missing-slots="message.missingSlots"
        :confirm-fields="message.confirmFields"
        :question="message.clarifyQuestion"
      />

      <!-- 2. Plans Recommendation Card -->
      <PlanCard
        v-if="hasPlans"
        :blocks="message.displayBlocks || []"
        :message-id="message.id"
        :trace-id="message.traceId"
        :feedback-saved="message.feedbackSaved"
        :feedback-rating="message.feedbackRating"
      />

      <!-- 3. Queried Orders List Card -->
      <OrderListCard
        v-if="hasOrders"
        :orders="message.displayBlocks || []"
      />

      <!-- 4. Action Status Card (Order / Booking / Payment) -->
      <ActionCard
        v-if="hasAction"
        :order-no="message.orderNo"
        :task-id="message.taskId"
        :blocks="message.displayBlocks"
        :text="message.text"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessage } from '@/types/chat'
import ClarifyCard from './ClarifyCard.vue'
import PlanCard from './PlanCard.vue'
import ActionCard from './ActionCard.vue'
import OrderListCard from './OrderListCard.vue'

const props = defineProps<{
  message: ChatMessage
}>()

const roleLabel = computed(() => {
  if (props.message.role === 'user') return '您'
  if (props.message.role === 'assistant') return '出行规划助手'
  return '系统通知'
})

const formattedText = computed(() => {
  const raw = props.message.text || ''
  // Basic line break and markdown bold parsing
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')
})

const hasPlans = computed(() => {
  return props.message.displayBlocks?.some(
    (b) => b && !b.orderNo && (b.planId || b.totalPrice !== undefined || b.score !== undefined)
  )
})

const hasOrders = computed(() => {
  return props.message.displayBlocks?.some((b) => b && b.orderNo && b.status)
})

const hasAction = computed(() => {
  return (
    !hasOrders.value &&
    (Boolean(props.message.orderNo) ||
      Boolean(props.message.taskId) ||
      props.message.responseType === 'TASK_PROGRESS')
  )
})
</script>

<style scoped>
.message-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  width: 100%;
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-row.system {
  justify-content: center;
}

.avatar-wrap {
  flex-shrink: 0;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.agent-avatar {
  background: linear-gradient(135deg, #e0f2fe, #bae6fd);
  border: 1px solid #7dd3fc;
}

.user-avatar {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border: 1px solid #bfdbfe;
}

.message-body {
  max-width: 82%;
  display: flex;
  flex-direction: column;
}

.message-row.user .message-body {
  align-items: flex-end;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.meta-role {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.meta-time {
  font-size: 11px;
  color: #94a3b8;
}

.trace-tag {
  font-family: monospace;
  font-size: 10px;
  color: #2563eb;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  padding: 1px 6px;
  border-radius: 4px;
}

.text-bubble {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.message-row.assistant .text-bubble {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  color: #1e293b;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
  border-top-left-radius: 4px;
}

.message-row.user .text-bubble {
  background: #2563eb;
  color: #ffffff;
  border-top-right-radius: 4px;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.2);
}

.message-row.system .text-bubble {
  background: #f1f5f9;
  color: #64748b;
  font-size: 12px;
  padding: 6px 14px;
  border-radius: 9999px;
}
</style>
