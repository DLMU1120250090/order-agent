<template>
  <el-dialog
    v-model="traceStore.showLabelModal"
    title="人工标定 (Ground Truth Labeling)"
    width="580px"
    destroy-on-close
  >
    <div class="label-form-container">
      <div class="form-tip">
        标定数据将沉淀至评测样本库，用于 CI 自动化评估计算意图命中率、槽位抽取准确率与端到端任务成功率。
      </div>

      <!-- Current Trace Runtime Actual Info Card -->
      <div class="runtime-info-card">
        <div class="runtime-card-header">
          <div class="runtime-title">
            <el-icon><InfoFilled /></el-icon>
            <span>当前 Trace 实际识别结果 (Runtime Actual)</span>
          </div>
          <el-button
            size="small"
            type="primary"
            link
            @click="prefillFromActual"
          >
            一键带入实际值
          </el-button>
        </div>

        <div class="runtime-content">
          <div v-if="currentSnapshot.userMessage" class="runtime-row">
            <span class="runtime-lbl">💬 用户发言:</span>
            <span class="runtime-val user-msg">“{{ currentSnapshot.userMessage }}”</span>
          </div>

          <div class="runtime-row intent-row">
            <div class="runtime-sub-item">
              <span class="runtime-lbl">🎯 识别意图:</span>
              <el-tag size="small" :type="currentSnapshot.actualIntent ? 'primary' : 'info'" effect="light">
                {{ formatIntentName(currentSnapshot.actualIntent) }}
              </el-tag>
            </div>

            <div class="runtime-sub-item">
              <span class="runtime-lbl">澄清动作:</span>
              <span class="clarify-tag">
                {{ currentSnapshot.actualClarifyAction === 'READY' ? '直接规划 (READY)' : (currentSnapshot.actualClarifyAction === 'ASK' ? '追问澄清 (ASK)' : (currentSnapshot.actualClarifyAction || '未触发')) }}
              </span>
            </div>
          </div>

          <div v-if="hasActualSlots" class="runtime-row">
            <span class="runtime-lbl">🧩 抽取槽位:</span>
            <div class="runtime-slots-list">
              <span v-if="currentSnapshot.actualSlots.departure" class="mini-slot-tag">
                出发: <strong>{{ currentSnapshot.actualSlots.departure }}</strong>
              </span>
              <span v-if="currentSnapshot.actualSlots.destination" class="mini-slot-tag">
                目的: <strong>{{ currentSnapshot.actualSlots.destination }}</strong>
              </span>
              <span v-if="currentSnapshot.actualSlots.departureDate" class="mini-slot-tag">
                日期: <strong>{{ currentSnapshot.actualSlots.departureDate }}</strong>
              </span>
              <span v-if="currentSnapshot.actualSlots.transportPreference" class="mini-slot-tag">
                偏好: <strong>{{ currentSnapshot.actualSlots.transportPreference }}</strong>
              </span>
            </div>
          </div>
        </div>
      </div>

      <el-form label-position="top" class="label-form">
        <!-- Expected Intent -->
        <el-form-item label="期望意图 (Expected Intent)" required>
          <el-select
            v-model="form.expectedIntent"
            placeholder="请选择标准意图"
            class="full-select"
          >
            <el-option
              v-for="item in INTENT_OPTIONS"
              :key="item.value"
              :label="`${item.label} (${item.value})`"
              :value="item.value"
            />
          </el-select>
        </el-form-item>

        <!-- Expected Clarify Action -->
        <el-form-item label="期望澄清动作 (Expected Clarify Action)">
          <el-radio-group v-model="form.expectedClarifyAction">
            <el-radio-button label="READY">直接规划 (READY)</el-radio-button>
            <el-radio-button label="ASK">追问澄清 (ASK)</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- Expected Slots -->
        <div class="slots-box">
          <div class="slots-box-title">期望必填槽位 (Expected Slots)</div>
          <div class="slots-grid">
            <el-form-item label="出发地">
              <el-input v-model="form.slots.departure" placeholder="例如：北京 / 上海" />
            </el-form-item>
            <el-form-item label="目的地">
              <el-input v-model="form.slots.destination" placeholder="例如：成都 / 杭州" />
            </el-form-item>
            <el-form-item label="出行日期">
              <el-input v-model="form.slots.departureDate" placeholder="YYYY-MM-DD" />
            </el-form-item>
            <el-form-item label="交通偏好">
              <el-select v-model="form.slots.transportPreference" placeholder="选择偏好" clearable>
                <el-option label="高铁优先 (train)" value="train" />
                <el-option label="航班优先 (flight)" value="flight" />
              </el-select>
            </el-form-item>
          </div>
        </div>

        <!-- Label Note -->
        <el-form-item label="标定备注 (Notes)">
          <el-input
            v-model="form.labelNote"
            type="textarea"
            :rows="2"
            placeholder="说明标定理由或边界 case 说明..."
          />
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="traceStore.showLabelModal = false">取消</el-button>
        <el-button
          type="primary"
          :loading="traceStore.isLabeling"
          @click="handleSubmit"
        >
          保存人工标定
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { useTraceStore } from '@/stores/trace'
import { formatIntentName } from '@/utils/trace'
import type { TraceLabelRequest } from '@/types/trace'

const traceStore = useTraceStore()

const currentSnapshot = computed(() => traceStore.currentSnapshot)

const hasActualSlots = computed(() => {
  const s = currentSnapshot.value?.actualSlots
  if (!s) return false
  return !!(s.departure || s.destination || s.departureDate || s.transportPreference)
})

const INTENT_OPTIONS = [
  { value: 'PLAN_RECOMMENDATION', label: '出行方案推荐' },
  { value: 'CLARIFY_NEEDED', label: '信息不足追问' },
  { value: 'PLAN_ADJUST', label: '调整方案' },
  { value: 'PLAN_BOOK', label: '确认下单' },
  { value: 'ORDER_QUERY', label: '查订单' },
  { value: 'ORDER_CHANGE', label: '改签申请' },
  { value: 'ORDER_CANCEL', label: '取消/退票' },
  { value: 'PRICE_MONITOR', label: '价格监控' },
  { value: 'CHECKLIST_EXPORT', label: '清单导出' },
  { value: 'OTHER', label: '闲聊/其他' },
]

const form = ref<{
  expectedIntent: string
  expectedClarifyAction: string
  slots: {
    departure: string
    destination: string
    departureDate: string
    transportPreference: string
  }
  labelNote: string
}>({
  expectedIntent: 'PLAN_RECOMMENDATION',
  expectedClarifyAction: 'READY',
  slots: {
    departure: '',
    destination: '',
    departureDate: '',
    transportPreference: '',
  },
  labelNote: '',
})

function prefillFromActual() {
  const snap = currentSnapshot.value
  if (!snap) return
  if (snap.actualIntent) {
    form.value.expectedIntent = snap.actualIntent
  }
  if (snap.actualClarifyAction) {
    form.value.expectedClarifyAction = snap.actualClarifyAction
  }
  if (snap.actualSlots) {
    if (snap.actualSlots.departure) form.value.slots.departure = snap.actualSlots.departure
    if (snap.actualSlots.destination) form.value.slots.destination = snap.actualSlots.destination
    if (snap.actualSlots.departureDate) form.value.slots.departureDate = snap.actualSlots.departureDate
    if (snap.actualSlots.transportPreference) form.value.slots.transportPreference = snap.actualSlots.transportPreference
  }
  ElMessage.success('已自动带入实际识别值，您可按需微调！')
}

// Auto pre-fill when modal opens
watch(
  () => traceStore.showLabelModal,
  (val) => {
    if (val && traceStore.currentTrace) {
      const t = traceStore.currentTrace
      const snap = traceStore.currentSnapshot

      if (t.expectedIntent || t.expectedClarifyAction || t.expectedSlots) {
        form.value.expectedIntent = t.expectedIntent || 'PLAN_RECOMMENDATION'
        form.value.expectedClarifyAction = t.expectedClarifyAction || 'READY'
        form.value.labelNote = t.labelNote || ''

        let existingSlots: any = t.expectedSlots
        if (typeof existingSlots === 'string') {
          try {
            existingSlots = JSON.parse(existingSlots)
          } catch {
            existingSlots = {}
          }
        }
        form.value.slots = {
          departure: existingSlots?.departure || '',
          destination: existingSlots?.destination || '',
          departureDate: existingSlots?.departureDate || existingSlots?.tripDate || '',
          transportPreference: existingSlots?.transportPreference || existingSlots?.preferred_transport || '',
        }
      } else {
        // 未标定时，优先把当前 Trace 实际识别出的意图和槽位填上
        form.value.expectedIntent = snap.actualIntent || 'PLAN_RECOMMENDATION'
        form.value.expectedClarifyAction = snap.actualClarifyAction || 'READY'
        form.value.labelNote = ''
        form.value.slots = {
          departure: snap.actualSlots?.departure || '',
          destination: snap.actualSlots?.destination || '',
          departureDate: snap.actualSlots?.departureDate || '',
          transportPreference: snap.actualSlots?.transportPreference || '',
        }
      }
    }
  }
)

async function handleSubmit() {
  if (!traceStore.selectedTraceId) return

  const payload: TraceLabelRequest = {
    expectedIntent: form.value.expectedIntent,
    expectedClarifyAction: form.value.expectedClarifyAction,
    expectedSlots: {
      departure: form.value.slots.departure || undefined,
      destination: form.value.slots.destination || undefined,
      departureDate: form.value.slots.departureDate || undefined,
      transportPreference: form.value.slots.transportPreference || undefined,
    },
    labelNote: form.value.labelNote || undefined,
  }

  try {
    await traceStore.submitLabel(traceStore.selectedTraceId, payload)
    ElMessage.success('人工标定保存成功！')
  } catch (err: any) {
    ElMessage.error(err?.message || '保存标定失败')
  }
}
</script>

<style scoped>
.label-form-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-tip {
  font-size: 12px;
  color: #64748b;
  background: #f1f5f9;
  padding: 8px 12px;
  border-radius: 6px;
  line-height: 1.45;
}

/* Runtime actual card */
.runtime-info-card {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
  padding: 10px 14px;
}

.runtime-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px dashed #bae6fd;
}

.runtime-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 700;
  color: #0369a1;
}

.runtime-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.runtime-row {
  display: flex;
  align-items: center;
  font-size: 12px;
  line-height: 1.4;
  flex-wrap: wrap;
  gap: 6px;
}

.runtime-row.intent-row {
  justify-content: flex-start;
  gap: 16px;
}

.runtime-sub-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.runtime-lbl {
  color: #475569;
  font-weight: 600;
  flex-shrink: 0;
}

.runtime-val.user-msg {
  color: #0f172a;
  background: #ffffff;
  padding: 1px 8px;
  border-radius: 4px;
  border: 1px solid #cbd5e1;
  font-weight: 500;
  word-break: break-all;
}

.clarify-tag {
  font-size: 11.5px;
  color: #0284c7;
  font-weight: 600;
  background: #ffffff;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid #bae6fd;
}

.runtime-slots-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.mini-slot-tag {
  font-size: 11px;
  color: #334155;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  padding: 1px 6px;
  border-radius: 4px;
}

.mini-slot-tag strong {
  color: #0284c7;
}

.label-form {
  margin-top: 6px;
}

.full-select {
  width: 100%;
}

.slots-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.slots-box-title {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 10px;
}

.slots-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.slots-grid .el-form-item {
  margin-bottom: 0;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
