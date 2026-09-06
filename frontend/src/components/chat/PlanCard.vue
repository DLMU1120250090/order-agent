<template>
  <div class="plans-container">
    <div class="plans-header">
      <div class="plans-badge">
        <el-icon><Guide /></el-icon>
        <span>Agent 推荐方案比选</span>
      </div>
      <span class="plans-count">共生成 {{ plans.length }} 套方案</span>
    </div>

    <!-- Cards Grid/List -->
    <div class="plan-cards">
      <div
        v-for="(plan, idx) in plans"
        :key="plan.planId || idx"
        class="plan-card"
        :class="{ recommended: idx === 0 }"
      >
        <!-- Card Top Bar -->
        <div class="card-top">
          <div class="plan-tag">
            <span class="plan-no">方案 {{ String.fromCharCode(65 + idx) }}</span>
            <span v-if="idx === 0" class="best-badge">首选推荐</span>
          </div>
          <div class="plan-price">
            <span class="price-symbol">¥</span>
            <span class="price-val">{{ plan.totalPrice }}</span>
          </div>
        </div>

        <!-- Legs Segment -->
        <div v-if="plan.legs && plan.legs.length > 0" class="legs-list">
          <div v-for="(leg, legIdx) in plan.legs" :key="legIdx" class="leg-item">
            <div class="leg-vehicle">
              <el-tag
                size="small"
                :type="leg.mode === 'FLIGHT' ? 'warning' : 'primary'"
                effect="light"
                class="vehicle-tag"
              >
                {{ leg.vehicle_no || leg.mode }}
              </el-tag>
            </div>
            <div class="leg-route">
              <div class="station-time">
                <span class="time">{{ leg.depart }}</span>
                <span class="station">{{ leg.from_station || leg.from_city }}</span>
              </div>
              <div class="route-arrow">
                <span class="duration">{{ plan.totalDurationH }}h</span>
                <div class="arrow-line"></div>
              </div>
              <div class="station-time text-right">
                <span class="time">{{ leg.arrive }}</span>
                <span class="station">{{ leg.to_station || leg.to_city }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Summary or Reason -->
        <div v-if="plan.summary || plan.reason" class="plan-summary">
          <span class="summary-text">{{ plan.summary || plan.reason }}</span>
        </div>

        <!-- Card Action Buttons -->
        <div class="card-actions">
          <el-button
            type="primary"
            size="small"
            class="select-btn"
            @click="selectThisPlan(idx + 1)"
          >
            选择此方案
          </el-button>
        </div>
      </div>
    </div>

    <!-- Bottom Global Actions -->
    <div class="plans-footer">
      <div class="quick-batch-actions">
        <el-button size="small" plain @click="refreshBatch">
          <el-icon><Refresh /></el-icon>
          换一批
        </el-button>
        <el-button size="small" plain @click="adjustCriteria">
          <el-icon><Operation /></el-icon>
          调整条件
        </el-button>
      </div>

      <!-- User Feedback Section (30% Evaluation Weight Loop) -->
      <div class="feedback-section">
        <div v-if="feedbackSaved" class="feedback-done">
          <el-icon><CircleCheckFilled class="text-green-500" /></el-icon>
          <span>反馈已记录 ({{ feedbackRating }} 星)</span>
        </div>
        <div v-else class="feedback-buttons">
          <span class="feedback-tip">方案是否满意：</span>
          <button
            type="button"
            class="feedback-btn like"
            title="满意，符合我的出行意图"
            @click="handleFeedback(5, 'LIKE')"
          >
            👍 满意
          </button>
          <button
            type="button"
            class="feedback-btn dislike"
            title="不满意，需优化"
            @click="openDislikeDialog"
          >
            👎 不满意
          </button>
        </div>
      </div>
    </div>

    <!-- Dislike Reason Dialog -->
    <el-dialog
      v-model="dislikeDialogVisible"
      title="请告诉我们哪里不满意"
      width="360px"
      append-to-body
    >
      <div class="dislike-form">
        <el-radio-group v-model="selectedDislikeReason" class="reason-group">
          <el-radio value="价格超出预期">价格超出预期</el-radio>
          <el-radio value="时刻不理想(太早/太晚)">时刻不理想 (太早/太晚)</el-radio>
          <el-radio value="交通方式不符合偏好">交通方式不符合偏好</el-radio>
          <el-radio value="其他原因">其他原因</el-radio>
        </el-radio-group>
      </div>
      <template #footer>
        <el-button size="small" @click="dislikeDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="confirmDislikeFeedback">
          提交反馈
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  blocks: any[]
  messageId: string
  traceId?: string
  feedbackSaved?: boolean
  feedbackRating?: number
}>()

const chatStore = useChatStore()
const dislikeDialogVisible = ref(false)
const selectedDislikeReason = ref('价格超出预期')

const plans = computed(() => {
  if (!Array.isArray(props.blocks)) return []
  return props.blocks.filter((b) => b && (b.legs || b.totalPrice !== undefined))
})

function selectThisPlan(planNo: number) {
  chatStore.sendMessage(`就订第${planNo}个`)
}

function refreshBatch() {
  chatStore.sendMessage('换一批')
}

function adjustCriteria() {
  chatStore.sendMessage('帮我调整出行条件')
}

function handleFeedback(rating: number, action: string, reason = '') {
  chatStore.submitFeedback(props.messageId, {
    planId: plans.value[0]?.planId,
    traceId: props.traceId,
    action,
    rating,
    reason,
  })
}

function openDislikeDialog() {
  dislikeDialogVisible.value = true
}

function confirmDislikeFeedback() {
  dislikeDialogVisible.value = false
  handleFeedback(2, 'DISLIKE', selectedDislikeReason.value)
}
</script>

<style scoped>
.plans-container {
  margin-top: 10px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
}

.plans-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.plans-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1e40af;
}

.plans-count {
  font-size: 11px;
  color: #94a3b8;
}

.plan-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plan-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 14px;
  transition: all 0.2s ease;
}

.plan-card:hover {
  border-color: #93c5fd;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.08);
}

.plan-card.recommended {
  background: #f0f7ff;
  border-color: #bfdbfe;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.plan-tag {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-no {
  font-weight: 700;
  font-size: 14px;
  color: #0f172a;
}

.best-badge {
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: #ffffff;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.plan-price {
  color: #ea580c;
  font-weight: 700;
}

.price-symbol {
  font-size: 12px;
}

.price-val {
  font-size: 18px;
}

.leg-item {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.leg-route {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.station-time {
  display: flex;
  flex-direction: column;
}

.time {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.station {
  font-size: 11.5px;
  color: #64748b;
}

.route-arrow {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 10px;
}

.duration {
  font-size: 10.5px;
  color: #94a3b8;
  margin-bottom: 2px;
}

.arrow-line {
  width: 60px;
  height: 2px;
  background: #cbd5e1;
  position: relative;
}

.arrow-line::after {
  content: '';
  position: absolute;
  right: 0;
  top: -3px;
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 6px solid #cbd5e1;
}

.plan-summary {
  font-size: 11px;
  color: #475569;
  background: #f1f5f9;
  padding: 4px 8px;
  border-radius: 6px;
  margin-bottom: 10px;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
}

.select-btn {
  border-radius: 6px;
  font-size: 12px;
}

.plans-footer {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e2e8f0;
}

.quick-batch-actions {
  display: flex;
  gap: 8px;
}

.feedback-section {
  display: flex;
  align-items: center;
}

.feedback-buttons {
  display: flex;
  align-items: center;
  gap: 6px;
}

.feedback-tip {
  font-size: 11px;
  color: #94a3b8;
}

.feedback-btn {
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.feedback-btn.like:hover {
  background: #f0fdf4;
  border-color: #22c55e;
  color: #15803d;
}

.feedback-btn.dislike:hover {
  background: #fef2f2;
  border-color: #ef4444;
  color: #b91c1c;
}

.feedback-done {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #16a34a;
}

.reason-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
