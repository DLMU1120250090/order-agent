<template>
  <div class="change-decision-card">
    <!-- Card Top Header -->
    <div class="card-header">
      <div class="header-left">
        <div class="header-badge">
          <el-icon><Switch /></el-icon>
          <span>改签方案对比决策矩阵</span>
        </div>
        <el-tag v-if="targetDate" size="small" type="success" effect="light" class="target-date-pill">
          📅 目标日期: {{ targetDate }}
        </el-tag>
      </div>

      <div class="header-right">
        <span v-if="orderNo" class="order-no-tag">单号: {{ orderNo }}</span>
      </div>
    </div>

    <!-- AI Recommendation Banner -->
    <div v-if="cleanReasonText || recommendedKindText" class="recommend-banner">
      <div class="banner-top">
        <div class="banner-badge">
          <el-icon><Opportunity /></el-icon>
          <span>AI 智选推荐</span>
        </div>
        <span class="recommend-title">
          {{ recommendedKindText }}
        </span>
      </div>
      <p v-if="cleanReasonText" class="banner-reason">{{ cleanReasonText }}</p>
    </div>

    <!-- Options Comparison Grid -->
    <div class="options-grid">
      <div
        v-for="(opt, idx) in normalizedOptions"
        :key="opt.kind || idx"
        class="option-item"
        :class="{ 'is-recommended': opt.isRecommended }"
      >
        <!-- Option Header -->
        <div class="option-header">
          <div class="option-title-box">
            <span class="option-letter">方案 {{ getOptionLetter(idx) }}</span>
            <span class="option-kind-name">{{ getKindName(opt.kind) }}</span>
          </div>
          <span v-if="opt.isRecommended" class="best-choice-badge">★ 最优推荐</span>
        </div>

        <!-- Loss & Cost Pill -->
        <div class="loss-row">
          <div class="loss-pill" :class="getLossClass(opt.total_loss)">
            <span class="loss-label">预计总损失:</span>
            <span class="loss-amount">¥{{ Math.abs(opt.total_loss || 0).toFixed(0) }}</span>
            <span v-if="(opt.total_loss || 0) < 0" class="saving-text">(节省)</span>
          </div>
        </div>

        <!-- Cost Breakdown -->
        <div class="fees-detail">
          <div v-if="opt.old_price" class="fee-line">
            <span class="fee-label">原票金额</span>
            <span class="fee-val">¥{{ opt.old_price }}</span>
          </div>
          <div v-if="opt.change_fee !== undefined && opt.kind === 'CHANGE'" class="fee-line">
            <span class="fee-label">改签手续费</span>
            <span class="fee-val">¥{{ opt.change_fee }}</span>
          </div>
          <div v-if="opt.refund_fee !== undefined && (opt.kind === 'CANCEL' || opt.kind === 'CANCEL_REBOOK')" class="fee-line">
            <span class="fee-label">退票手续费</span>
            <span class="fee-val">¥{{ opt.refund_fee }}</span>
          </div>
        </div>

        <!-- Risks & Notes -->
        <div v-if="opt.risks && opt.risks.length > 0" class="risks-box">
          <div v-for="(risk, rIdx) in opt.risks" :key="rIdx" class="risk-item">
            <el-icon class="risk-icon"><Warning /></el-icon>
            <span class="risk-text">{{ risk }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick Action Buttons -->
    <div class="card-actions">
      <div class="actions-left">
        <span class="action-prompt">快捷指令:</span>
        <el-button
          type="primary"
          size="default"
          :loading="chatStore.isSending"
          class="action-btn action-btn-change"
          @click="handleAction('确认改签')"
        >
          <el-icon><Check /></el-icon>
          确认改签 (推荐)
        </el-button>

        <el-button
          type="danger"
          plain
          size="default"
          :loading="chatStore.isSending"
          class="action-btn"
          @click="handleAction('确认退票')"
        >
          <el-icon><Close /></el-icon>
          申请退票
        </el-button>

        <el-button
          size="default"
          plain
          :loading="chatStore.isSending"
          class="action-btn"
          @click="handleAction('保持原行程')"
        >
          保持原行程
        </el-button>
      </div>

      <span class="action-note">点击按钮将自动向助手发送执行指令</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Switch, Opportunity, Warning, Check, Close } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import type { ChatMessage } from '@/types/chat'

const props = defineProps<{
  message: ChatMessage
  block?: any
}>()

const chatStore = useChatStore()

// 提取决策 Block
const decisionData = computed(() => {
  if (props.block && props.block.blockType === 'CHANGE_DECISION') {
    return props.block
  }
  const blocks = props.message.displayBlocks || []
  const found = blocks.find((b: any) => b && b.blockType === 'CHANGE_DECISION')
  if (found) return found

  // 如果 blocks 包含单个选项
  const hasOptions = blocks.some((b: any) => b && b.kind && ['KEEP', 'CANCEL', 'CHANGE', 'CANCEL_REBOOK'].includes(b.kind))
  if (hasOptions) {
    const rawText = props.message.text || ''
    let reason = ''
    const match = rawText.match(/推荐[：:]\s*([^\n\r]+)/)
    if (match) {
      reason = match[1].trim()
    }
    return {
      orderNo: props.message.orderNo,
      reason: reason,
      options: blocks.filter((b: any) => b && b.kind),
    }
  }

  // 兜底：从原生文本解析（兼容历史记录）
  return parseFromText(props.message.text || '')
})

function parseFromText(text: string) {
  const options: any[] = []
  const lines = text.split('\n')

  let currentOpt: any = null
  let reason = ''
  let orderNo = ''

  const orderMatch = text.match(/ORD\d+/)
  if (orderMatch) orderNo = orderMatch[0]

  for (const line of lines) {
    const trimmed = line.trim()
    const optMatch = trimmed.match(/方案([A-D])\s+([^：:]+)[：:]\s*损失\s*¥?(-?\d+)/)
    if (optMatch) {
      if (currentOpt) options.push(currentOpt)
      const letter = optMatch[1]
      const name = optMatch[2]
      const loss = parseFloat(optMatch[3])
      const kindMap: Record<string, string> = {
        '保持原行程': 'KEEP',
        '取消退票': 'CANCEL',
        '改签': 'CHANGE',
        '取消重买': 'CANCEL_REBOOK',
      }
      currentOpt = {
        kind: kindMap[name] || (letter === 'A' ? 'KEEP' : letter === 'B' ? 'CANCEL' : letter === 'C' ? 'CHANGE' : 'CANCEL_REBOOK'),
        total_loss: loss,
        risks: [],
      }
      continue
    }

    if (trimmed.startsWith('风险:') || trimmed.startsWith('风险：')) {
      const r = trimmed.replace(/^风险[：:]\s*/, '')
      if (currentOpt) {
        currentOpt.risks.push(r)
      }
      continue
    }

    if (trimmed.startsWith('推荐:') || trimmed.startsWith('推荐：')) {
      reason = trimmed.replace(/^推荐[：:]\s*/, '').trim()
    }
  }
  if (currentOpt) options.push(currentOpt)

  return {
    orderNo,
    reason,
    options,
  }
}

const orderNo = computed(() => {
  return decisionData.value?.orderNo || props.message.orderNo || ''
})

const targetDate = computed(() => {
  return decisionData.value?.targetDate || ''
})

const recommendationReason = computed(() => {
  return decisionData.value?.reason || ''
})

const cleanReasonText = computed(() => {
  let r = recommendationReason.value || ''
  const match = r.match(/推荐[：:]\s*([^\n\r]+)/)
  if (match) {
    r = match[1]
  }
  return r
    .replace(/^推荐方案[：:]\s*/, '')
    .replace(/回复.*$/, '')
    .replace(/[─\-]{5,}/g, '')
    .replace(/🔀.*对比/, '')
    .trim()
})

const recommendedKindText = computed(() => {
  const r = recommendationReason.value || ''
  if (r.includes('改签')) return '推荐方案: 办理改签'
  if (r.includes('退票')) return '推荐方案: 取消退票'
  if (r.includes('重买')) return '推荐方案: 取消重买'
  return '推荐方案: 办理改签'
})

const normalizedOptions = computed(() => {
  const rawList = decisionData.value?.options || []
  if (rawList.length === 0) {
    // 默认提供 ABCD 四种候选
    return [
      { kind: 'KEEP', total_loss: 0, risks: ['退票后行程取消，出行需求未满足'], isRecommended: false },
      { kind: 'CANCEL', total_loss: 12, risks: ['退票后行程取消，出行需求未满足'], isRecommended: false },
      { kind: 'CHANGE', total_loss: 0, risks: ['改签费多不退少补', '新时刻以实际票面为准'], isRecommended: true },
      { kind: 'CANCEL_REBOOK', total_loss: 12, risks: ['新票为估算价，实际以支付为准', '建议先锁新票再退旧票'], isRecommended: false },
    ]
  }

  const recKind = decisionData.value?.recommendedKind || 'CHANGE'

  return rawList.map((opt: any) => {
    const k = typeof opt.kind === 'string' ? opt.kind : (opt.kind?.value || 'CHANGE')
    const isRec = k === recKind || (recommendationReason.value.includes('改签') && k === 'CHANGE')
    return {
      ...opt,
      kind: k,
      isRecommended: isRec,
    }
  })
})

function getOptionLetter(idx: number | string): string {
  const n = typeof idx === 'number' ? idx : parseInt(String(idx), 10) || 0
  return String.fromCharCode(65 + n)
}

function getKindName(kind: string): string {
  switch (kind) {
    case 'KEEP': return '保持原行程'
    case 'CANCEL': return '取消退票'
    case 'CHANGE': return '办理改签'
    case 'CANCEL_REBOOK': return '取消重买'
    default: return kind
  }
}

function getLossClass(loss: number): string {
  if (loss === 0) return 'loss-zero'
  if (loss < 0) return 'loss-saving'
  return 'loss-positive'
}

function handleAction(cmd: string) {
  if (chatStore.isSending) return
  chatStore.sendMessage(cmd)
}
</script>

<style scoped>
.change-decision-card {
  background: #ffffff;
  border: 1px solid #bae6fd;
  border-radius: 14px;
  padding: 16px;
  margin-top: 8px;
  box-shadow: 0 4px 16px rgba(14, 165, 233, 0.08);
  max-width: 680px;
}

/* Header */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13.5px;
  font-weight: 700;
  color: #0284c7;
}

.target-date-pill {
  font-weight: 600;
}

.order-no-tag {
  font-size: 11px;
  color: #64748b;
  background: #f8fafc;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  font-family: monospace;
}

/* Recommendation Banner */
.recommend-banner {
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 14px;
}

.banner-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.banner-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #22c55e;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
}

.recommend-title {
  font-size: 13px;
  font-weight: 700;
  color: #166534;
}

.banner-reason {
  margin: 0;
  font-size: 12px;
  color: #15803d;
  line-height: 1.45;
}

/* Options Grid */
.options-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}

@media (max-width: 600px) {
  .options-grid {
    grid-template-columns: 1fr;
  }
}

.option-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.2s ease;
}

.option-item.is-recommended {
  background: #ffffff;
  border: 1.5px solid #38bdf8;
  box-shadow: 0 2px 10px rgba(56, 189, 248, 0.15);
}

.option-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.option-title-box {
  display: flex;
  align-items: center;
  gap: 6px;
}

.option-letter {
  font-size: 11px;
  font-weight: 800;
  background: #e2e8f0;
  color: #475569;
  padding: 1px 6px;
  border-radius: 4px;
}

.option-item.is-recommended .option-letter {
  background: #0284c7;
  color: #ffffff;
}

.option-kind-name {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.best-choice-badge {
  font-size: 10.5px;
  font-weight: 700;
  color: #0284c7;
  background: #e0f2fe;
  padding: 1px 6px;
  border-radius: 4px;
}

/* Loss Row */
.loss-row {
  display: flex;
  align-items: center;
}

.loss-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  padding: 3px 8px;
  border-radius: 6px;
}

.loss-zero {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.loss-positive {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}

.loss-saving {
  background: #faf5ff;
  color: #7e22ce;
  border: 1px solid #e9d5ff;
}

.loss-amount {
  font-size: 13px;
  font-weight: 800;
}

.saving-text {
  font-size: 11px;
  font-weight: 600;
}

/* Fees Detail */
.fees-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fee-line {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #64748b;
}

.fee-val {
  font-weight: 600;
  color: #334155;
}

/* Risks */
.risks-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: #ffffff;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px dashed #e2e8f0;
}

.risk-item {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

.risk-icon {
  font-size: 11.5px;
  color: #f59e0b;
  margin-top: 1px;
  flex-shrink: 0;
}

.risk-text {
  font-size: 11px;
  color: #64748b;
  line-height: 1.35;
}

/* Action Buttons */
.card-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
}

.actions-left {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.action-prompt {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.action-btn-change {
  font-weight: 700;
}

.action-note {
  font-size: 11px;
  color: #94a3b8;
}
</style>
