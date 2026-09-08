<template>
  <div v-if="computedSlotGroups.length > 0 || isConfirmMode" class="clarify-card">
    <div class="clarify-header">
      <el-icon class="clarify-icon"><Warning /></el-icon>
      <span class="clarify-title">{{ headerTitle }}</span>
    </div>

    <!-- Suggested quick selection pill tags -->
    <div v-if="computedSlotGroups.length > 0" class="slot-groups">
      <div v-for="group in computedSlotGroups" :key="group.slot" class="slot-group">
        <span class="slot-label">{{ group.label }}：</span>
        <div class="pill-tags">
          <el-tooltip
            v-for="opt in group.options"
            :key="opt.label"
            :content="opt.tip"
            :disabled="!opt.tip"
            placement="top"
            :show-after="150"
          >
            <button
              type="button"
              class="pill-tag"
              :class="{ active: isOptionActive(group.slot, opt.value) }"
              @click="selectOption(group.slot, opt.value)"
            >
              {{ opt.label }}
            </button>
          </el-tooltip>

          <!-- 乘车人快速新增按钮 -->
          <button
            v-if="group.slot === 'passengers'"
            type="button"
            class="pill-tag add-passenger-pill"
            @click="showPassengerModal = true"
          >
            <el-icon class="add-icon"><Plus /></el-icon>
            <span>添加新乘车人</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Confirm button -->
    <div class="clarify-actions">
      <el-button
        v-if="isConfirmMode"
        size="small"
        @click="confirmDefault"
      >
        按此偏好继续 (好)
      </el-button>
      <el-button
        type="primary"
        size="small"
        :disabled="Object.keys(selectedSlots).length === 0"
        @click="confirmClarify"
      >
        确认调整并发送
      </el-button>
    </div>

    <PassengerModal v-model="showPassengerModal" @saved="handlePassengerSaved" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Warning, Plus } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import { useMemoryStore } from '@/stores/memory'
import PassengerModal from './PassengerModal.vue'

interface OptionItem {
  label: string
  value: string
  tip?: string
}

interface SlotGroupItem {
  slot: string
  label: string
  options: OptionItem[]
}

const props = defineProps<{
  missingSlots?: string[]
  confirmFields?: string[]
  question?: string
}>()

const chatStore = useChatStore()
const memoryStore = useMemoryStore()
const selectedSlots = reactive<Record<string, string>>({})
const selectedPassengers = ref<string[]>([])
const showPassengerModal = ref(false)

onMounted(() => {
  if (!memoryStore.profile) {
    memoryStore.fetchProfile()
  }
})

const presetSlotGroups: SlotGroupItem[] = [
  {
    slot: 'passengers',
    label: '乘车人员',
    options: [
      { label: '👤 本人出行 (1人)', value: '本人出行 (1人)', tip: '当前登录账号本人出行，预订 1 张票' },
      { label: '👥 2人同行', value: '2人同行', tip: '双人同行，如本人与伴侣或朋友' },
      { label: '👨‍👩‍👧 家庭/多人 (3人+)', value: '家庭/多人', tip: '3人及以上结伴出游或家庭出行' },
    ],
  },
  {
    slot: 'transportMode',
    label: '交通偏好',
    options: [
      { label: '高铁优先', value: '高铁优先', tip: '优先推荐高速动车组（G/D 字头），准点便捷' },
      { label: '机票优先', value: '机票优先', tip: '优先推荐民航客机，中长途跨省出行快捷直达' },
      { label: '普通火车', value: '火车优先', tip: '普速列车/软卧硬卧，经济实惠，适合慢游或夜行晨至' },
      { label: '无特别偏好', value: '无特别偏好', tip: '综合对比高铁与民航等多种出行方式，择优推荐' },
    ],
  },
  {
    slot: 'budget',
    label: '预算范围',
    options: [
      { label: '经济型', value: '经济型', tip: '动态匹配当日低价方案（P30 分位数），追求高性价比' },
      { label: '舒适型', value: '舒适型', tip: '兼顾发车时刻与旅途舒适（P70 分位数），均衡品质体验' },
      { label: '高端型', value: '高端型', tip: '优选全价商务座或头等舱，空间宽敞与尊享权益优先' },
      { label: '不限预算', value: '不限预算', tip: '不做价格硬约束，优先综合耗时最短与行程最优' },
    ],
  },
  {
    slot: 'travelStyle',
    label: '出行风格',
    options: [
      { label: '商务差旅', value: '商务', tip: '首选准点直达、耗时最短车次，便于车上移动办公与会务签到' },
      { label: '休闲度假', value: '休闲', tip: '避开清晨早班，适中时间从容起程，旅途轻松不赶路' },
      { label: '亲子家庭', value: '亲子', tip: '优选直达免换乘折腾，车厢环境宽敞，更方便照顾儿童与家人' },
      { label: '紧凑打卡', value: '紧凑', tip: '早出晚归、游玩效率最高，适合周末短假高密度景点打卡' },
      { label: '美食探索', value: '美食', tip: '行程到达时刻紧密贴合正餐饭点，便于直奔当地特色美食' },
      { label: '购物扫街', value: '购物', tip: '到达站点紧邻核心繁华商圈，行李搬运与商圈穿梭更轻松' },
    ],
  },
  {
    slot: 'tripDate',
    label: '出行日期',
    options: [
      { label: '今天出发', value: '今天出发', tip: '即时应急出行，智能检索今天剩余最新可用班次' },
      { label: '明天出发', value: '明天出发', tip: '明天启程，兼顾充裕余票与较佳发车时刻' },
      { label: '后天出发', value: '后天出发', tip: '提前两天规划，席位与时刻选择空间更充裕' },
      { label: '本周末', value: '本周末', tip: '规划周五晚或周六晨出发的双休短途出游' },
    ],
  },
  {
    slot: 'destination',
    label: '目的城市',
    options: [
      { label: '上海', value: '上海', tip: '魔都国际大都市，外滩、陆家嘴与迪士尼' },
      { label: '北京', value: '北京', tip: '千年古都，故宫、长城、国博与胡同文化' },
      { label: '成都', value: '成都', tip: '天府之国慢生活，大熊猫基地与川味火锅' },
      { label: '杭州', value: '杭州', tip: '人间天堂西湖畔，江南水乡与灵隐禅意' },
      { label: '广州', value: '广州', tip: '千年商都广府韵，早茶夜市与珠江夜景' },
      { label: '深圳', value: '深圳', tip: '创新活力之都，莲花山、大梅沙与科技体验' },
      { label: '西安', value: '西安', tip: '十三朝古都，兵马俑、大唐不夜城与长安古意' },
      { label: '武汉', value: '武汉', tip: '九省通衢江城，黄鹤楼、东湖与过早热干面' },
      { label: '重庆', value: '重庆', tip: '魔幻 8D 山城，洪崖洞夜景与地道老火锅' },
    ],
  },
]

const isConfirmMode = computed(() => {
  return Boolean(
    props.confirmFields &&
    props.confirmFields.length > 0 &&
    (!props.missingSlots || props.missingSlots.length === 0)
  )
})

const headerTitle = computed(() => {
  if (isConfirmMode.value) {
    return '请确认或快捷调整出行偏好：'
  }
  return '需要补充出行信息：'
})

const visibleSlotGroups = computed(() => {
  const needed = new Set<string>()
  if (Array.isArray(props.missingSlots)) {
    props.missingSlots.forEach((s) => s && needed.add(s))
  }
  if (Array.isArray(props.confirmFields)) {
    props.confirmFields.forEach((s) => s && needed.add(s))
  }

  // If specific slots or confirmFields are requested, show only those!
  if (needed.size > 0) {
    const matched = presetSlotGroups.filter((g) => needed.has(g.slot))
    if (matched.length > 0) return matched
  }

  // Fallback: If neither missingSlots nor confirmFields were specified,
  // show common preference groups, but exclude tripDate/destination since they should only show when explicitly missing!
  return presetSlotGroups.filter((g) => g.slot !== 'tripDate' && g.slot !== 'destination')
})

const computedSlotGroups = computed(() => {
  return visibleSlotGroups.value.map((g) => {
    if (g.slot !== 'passengers') return g
    const baseOptions = [...g.options]
    const registered = memoryStore.profile?.passengers || []
    const extraOptions: OptionItem[] = []
    for (const p of registered) {
      const pName = p.name || (p.role === 'self' ? '本人' : '乘客')
      const isSelf = p.role === 'self' || String(p.passenger_id) === '0'
      const label = isSelf ? `👤 ${pName}(本人)` : `🏷️ ${pName}`
      if (!baseOptions.some((b) => b.value === pName)) {
        extraOptions.push({
          label,
          value: pName,
          tip: `证件号: ${p.id_no ? p.id_no.slice(0, 6) + '******' + p.id_no.slice(-4) : '已登记'} (${isSelf ? '本人' : '同行人'})`,
        })
      }
    }
    return {
      ...g,
      options: [...baseOptions, ...extraOptions],
    }
  })
})

function isOptionActive(slot: string, val: string): boolean {
  if (slot === 'passengers') {
    return selectedPassengers.value.includes(val)
  }
  return selectedSlots[slot] === val
}

function selectOption(slot: string, val: string) {
  if (slot === 'passengers') {
    const idx = selectedPassengers.value.indexOf(val)
    if (idx >= 0) {
      selectedPassengers.value.splice(idx, 1)
    } else {
      selectedPassengers.value.push(val)
    }
    if (selectedPassengers.value.length > 0) {
      selectedSlots['passengers'] = selectedPassengers.value.join('、')
    } else {
      delete selectedSlots['passengers']
    }
    return
  }

  if (selectedSlots[slot] === val) {
    delete selectedSlots[slot]
  } else {
    selectedSlots[slot] = val
  }
}

function handlePassengerSaved(p: any) {
  const name = p.name
  if (!selectedPassengers.value.includes(name)) {
    selectedPassengers.value.push(name)
    selectedSlots['passengers'] = selectedPassengers.value.join('、')
  }
}

function confirmDefault() {
  chatStore.sendMessage('好')
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

.add-passenger-pill {
  background: #ecfdf5;
  border: 1px dashed #10b981;
  color: #047857;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.add-passenger-pill:hover {
  background: #d1fae5;
  border-color: #059669;
}

.add-icon {
  font-size: 11px;
}

.clarify-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
