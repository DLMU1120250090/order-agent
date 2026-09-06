<template>
  <div class="clarify-card">
    <div class="clarify-header">
      <el-icon class="clarify-icon"><Warning /></el-icon>
      <span class="clarify-title">需要补充出行信息：</span>
    </div>

    <!-- Suggested quick selection pill tags -->
    <div class="slot-groups">
      <div v-for="group in presetSlotGroups" :key="group.slot" class="slot-group">
        <span class="slot-label">{{ group.label }}：</span>
        <div class="pill-tags">
          <button
            v-for="opt in group.options"
            :key="opt"
            type="button"
            class="pill-tag"
            :class="{ active: selectedSlots[group.slot] === opt }"
            @click="selectOption(group.slot, opt)"
          >
            {{ opt }}
          </button>
        </div>
      </div>
    </div>

    <!-- Confirm button -->
    <div class="clarify-actions">
      <el-button
        type="primary"
        size="small"
        :disabled="Object.keys(selectedSlots).length === 0"
        @click="confirmClarify"
      >
        确认补充并继续
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  missingSlots?: string[]
  question?: string
}>()

const chatStore = useChatStore()
const selectedSlots = reactive<Record<string, string>>({})

const presetSlotGroups = [
  {
    slot: 'transportMode',
    label: '交通偏好',
    options: ['高铁优先', '机票优先', '卧铺动卧', '无特别偏好'],
  },
  {
    slot: 'budget',
    label: '预算范围',
    options: ['经济型(¥500内)', '舒适型(¥1000内)', '不限预算'],
  },
  {
    slot: 'tripDate',
    label: '出行时段',
    options: ['明天出发', '周五晚上', '周六上午', '下周二'],
  },
]

function selectOption(slot: string, opt: string) {
  if (selectedSlots[slot] === opt) {
    delete selectedSlots[slot]
  } else {
    selectedSlots[slot] = opt
  }
}

function confirmClarify() {
  const parts = Object.values(selectedSlots)
  if (parts.length > 0) {
    chatStore.sendMessage(`我选择：${parts.join('，')}`)
  }
}
</script>

<style scoped>
.clarify-card {
  margin-top: 10px;
  background: #fffbeb;
  border: 1px solid #fef3c7;
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.clarify-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #b45309;
}

.clarify-icon {
  font-size: 16px;
}

.slot-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.slot-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.slot-label {
  font-size: 12px;
  color: #78350f;
  font-weight: 500;
  min-width: 60px;
}

.pill-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pill-tag {
  background: #ffffff;
  border: 1px solid #fde68a;
  color: #92400e;
  padding: 3px 10px;
  border-radius: 9999px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.pill-tag:hover {
  background: #fef3c7;
  border-color: #f59e0b;
}

.pill-tag.active {
  background: #f59e0b;
  color: #ffffff;
  border-color: #f59e0b;
  font-weight: 600;
}

.clarify-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}
</style>
