<template>
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="480px"
    destroy-on-close
    append-to-body
  >
    <div class="passenger-form-container">
      <div class="form-tip" :class="{ 'self-tip': isSelf }">
        <el-icon class="tip-icon"><InfoFilled /></el-icon>
        <div class="tip-content">
          <div class="tip-title">{{ tipTitle }}</div>
          <div class="tip-desc">{{ tipDesc }}</div>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="passenger-form">
        <el-form-item label="真实姓名" prop="name" required>
          <el-input v-model="form.name" placeholder="请输入乘车人真实中文姓名" maxlength="20" clearable />
        </el-form-item>

        <el-form-item label="证件类型" prop="id_type">
          <el-select v-model="form.id_type" class="full-width">
            <el-option label="居民身份证" value="身份证" />
            <el-option label="护照" value="护照" />
            <el-option label="港澳居民来往内地通行证" value="回乡证" />
            <el-option label="台湾居民来往大陆通行证" value="台胞证" />
          </el-select>
        </el-form-item>

        <el-form-item label="证件号码" prop="id_no" required>
          <el-input
            v-model="form.id_no"
            placeholder="请输入 18 位身份证号码"
            maxlength="18"
            clearable
          />
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="isSubmitting" @click="handleSubmit">
          {{ isEdit ? '保存档案' : '保存并选用' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { memoryApi } from '@/api/memory'
import { useMemoryStore } from '@/stores/memory'

const props = defineProps<{
  modelValue: boolean
  passengerData?: any
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'saved', passenger: any): void
}>()

const memoryStore = useMemoryStore()
const formRef = ref<FormInstance>()
const isSubmitting = ref(false)

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit('update:modelValue', val),
})

const isEdit = computed(() => Boolean(props.passengerData && props.passengerData.passenger_id))
const isSelf = computed(() => Boolean(props.passengerData && (String(props.passengerData.passenger_id) === '0' || props.passengerData.role === 'self')))

const dialogTitle = computed(() => {
  if (!isEdit.value) return '添加同行乘车人 (实名信息补全)'
  return isSelf.value ? '编辑本人实名档案 (Passenger 0)' : '编辑同行乘车人档案'
})

const tipTitle = computed(() => {
  if (!isEdit.value) return '新增同行乘车人登记'
  return isSelf.value ? '正在维护：本人实名档案' : '正在维护：同行乘车人档案'
})

const tipDesc = computed(() => {
  if (isSelf.value) {
    return '系统核心本人档案（Passenger 0），实名信息将用于您本人车票预订。'
  }
  return '根据铁路与民航实名制要求，登记后将自动收录至您的同行乘客簿，可在购票时快速选用。'
})

const form = reactive({
  name: '',
  id_type: '身份证',
  id_no: '',
  age_group: 'adult',
})

watch(
  () => props.modelValue,
  (val) => {
    if (val && props.passengerData) {
      form.name = props.passengerData.name || ''
      form.id_type = props.passengerData.id_type || '身份证'
      form.id_no = props.passengerData.id_no || ''
      form.age_group = props.passengerData.age_group || 'adult'
    } else if (val) {
      form.name = ''
      form.id_type = '身份证'
      form.id_no = ''
      form.age_group = 'adult'
    }
  },
  { immediate: true }
)

const rules = {
  name: [{ required: true, message: '请输入乘车人姓名', trigger: 'blur' }],
  id_no: [
    { required: true, message: '请输入证件号码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: any) => {
        if (form.id_type === '身份证' && !/^[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]$/.test(value.trim())) {
          callback(new Error('请输入合法的 18 位身份证号码'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    isSubmitting.value = true
    try {
      const payload = {
        name: form.name.trim(),
        id_type: form.id_type,
        id_no: form.id_no.trim(),
        role: isSelf.value ? 'self' : 'others',
        age_group: form.age_group,
      }
      let updatedProfile
      if (isEdit.value && props.passengerData?.passenger_id) {
        updatedProfile = await memoryApi.updatePassenger(props.passengerData.passenger_id, payload)
        ElMessage.success(`乘车人 ${form.name} 信息已更新！`)
      } else {
        updatedProfile = await memoryApi.addPassenger(payload)
        ElMessage.success(`乘车人 ${form.name} 已登记成功！`)
      }
      memoryStore.profile = updatedProfile
      emit('saved', { ...payload, passenger_id: props.passengerData?.passenger_id })
      dialogVisible.value = false
    } catch (err: any) {
      console.error('Failed to save passenger:', err)
      ElMessage.error(err?.response?.data?.detail || '保存乘车人失败，请重试')
    } finally {
      isSubmitting.value = false
    }
  })
}
</script>

<style scoped>
.passenger-form-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-tip {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  padding: 10px 14px;
  color: #166534;
}

.form-tip.self-tip {
  background: #eff6ff;
  border-color: #bfdbfe;
  color: #1e40af;
}

.tip-icon {
  font-size: 16px;
  color: #16a34a;
  margin-top: 2px;
  flex-shrink: 0;
}

.form-tip.self-tip .tip-icon {
  color: #2563eb;
}

.tip-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tip-title {
  font-size: 12.5px;
  font-weight: 700;
}

.tip-desc {
  font-size: 11.5px;
  line-height: 1.45;
  opacity: 0.9;
}

.passenger-form {
  margin-top: 4px;
}

.full-width {
  width: 100%;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
