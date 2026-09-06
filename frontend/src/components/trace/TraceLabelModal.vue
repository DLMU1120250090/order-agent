<template>
  <el-dialog
    v-model="traceStore.showLabelModal"
    title="人工标定金标准答案 (Ground Truth Labeling)"
    width="560px"
    destroy-on-close
  >
    <div class="label-form-container">
      <div class="form-tip">
        标定数据将沉淀至评测样本库，用于 CI 自动化评估计算意图命中率、槽位抽取准确率与端到端任务成功率。
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
          保存标定金标准
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useTraceStore } from '@/stores/trace'
import type { TraceLabelRequest } from '@/types/trace'

const traceStore = useTraceStore()

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

// Auto pre-fill when modal opens
watch(
  () => traceStore.showLabelModal,
  (val) => {
    if (val && traceStore.currentTrace) {
      const t = traceStore.currentTrace
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
    ElMessage.success('金标准标定保存成功！')
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
