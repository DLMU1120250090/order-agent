<template>
  <div class="profile-container">
    <!-- Top Action Bar -->
    <div class="profile-header">
      <div class="user-meta-summary">
        <div class="user-avatar-badge">👤</div>
        <div class="user-meta-text">
          <div class="user-title">
            <span>用户 ID: {{ profile?.user_id }}</span>
            <span class="city-tag">常驻城市: {{ profile?.home_city || '未设置' }}</span>
            <span class="budget-tag">预算档位: {{ profile?.budget_level || 'standard' }}</span>
          </div>
          <div class="user-sub">
            包含 {{ profile?.passengers?.length || 0 }} 位同行乘客，L1 确定性记忆直接约束规划搜索空间
          </div>
        </div>
      </div>

      <el-button type="primary" @click="openEditDrawer">
        <el-icon><Edit /></el-icon>
        编辑画像与偏好
      </el-button>
    </div>

    <!-- Main Grid: Global Preferences + Passenger Roster -->
    <div class="profile-grid">
      <!-- Left Card: Self Global Preferences -->
      <div class="pref-card">
        <div class="card-header">
          <div class="card-title">
            <el-icon><UserFilled /></el-icon>
            <span>本人全局画像偏好</span>
          </div>
          <span class="card-tag">全局默认</span>
        </div>

        <div v-if="Object.keys(displayPreferences).length === 0" class="empty-pref">
          <div class="empty-hint">暂未配置显式出行偏好</div>
          <div class="empty-sub">Agent 会在对话规划与实际订票过程中自动学习沉淀</div>
        </div>

        <div v-else class="pref-items-list">
          <div
            v-for="(val, key) in displayPreferences"
            :key="key"
            class="pref-item-row"
          >
            <div class="pref-key-box">
              <span class="pref-key">{{ formatKey(String(key)) }}</span>
              <span class="pref-key-raw">{{ key }}</span>
            </div>
            <div class="pref-val-box">
              <span class="pref-val">{{ formatVal(val) }}</span>
            </div>
          </div>
        </div>

        <!-- Feedback & Satisfaction Statistics Footer -->
        <div v-if="hasFeedback" class="feedback-stats-footer">
          <div class="stats-header">
            <span class="stats-title">方案交互满意度记录:</span>
          </div>
          <div class="stats-pills">
            <el-tag v-if="feedbackStats.positive > 0" size="small" type="success" effect="light" class="stat-pill">
              👍 采纳满意 {{ feedbackStats.positive }} 次
            </el-tag>
            <el-tag v-if="feedbackStats.negative > 0" size="small" type="danger" effect="light" class="stat-pill">
              👎 待优化反馈 {{ feedbackStats.negative }} 次
            </el-tag>
            <el-tag v-if="feedbackStats.switches > 0" size="small" type="info" effect="plain" class="stat-pill">
              🔄 换一批 {{ feedbackStats.switches }} 次
            </el-tag>
          </div>
        </div>
      </div>

      <!-- Right Card: Passenger List & Individual Preferences -->
      <div class="pref-card">
        <div class="card-header">
          <div class="card-title">
            <el-icon><User /></el-icon>
            <span>同行乘客簿与专属偏好 (Passenger Roster)</span>
          </div>
          <div class="card-actions">
            <el-button size="small" type="primary" plain @click="openAddPassengerModal">
              <el-icon><Plus /></el-icon>
              添加乘车人
            </el-button>
          </div>
        </div>

        <div v-if="!profile?.passengers || profile.passengers.length === 0" class="empty-pref">
          暂无已登记的同行乘客信息
        </div>

        <div v-else class="passenger-list">
          <div
            v-for="p in profile.passengers"
            :key="p.passenger_id"
            class="passenger-item"
          >
            <div class="passenger-top">
              <div class="p-name-role">
                <span class="p-name">{{ p.name || p.passenger_id }}</span>
                <el-tag
                  size="small"
                  :type="p.role === 'self' || String(p.passenger_id) === '0' ? 'primary' : 'success'"
                  effect="light"
                >
                  {{ p.role === 'self' || String(p.passenger_id) === '0' ? '本人 (Self)' : '同行人 (Others)' }}
                </el-tag>
                <span class="p-id-pill">{{ p.passenger_id }}</span>
              </div>
              <div class="p-actions">
                <el-button size="small" link type="primary" @click="openEditPassengerModal(p)">
                  <el-icon><Edit /></el-icon> 编辑
                </el-button>
                <el-popconfirm
                  v-if="p.role !== 'self' && String(p.passenger_id) !== '0'"
                  title="确认要从同行乘车簿中删除该乘客吗？"
                  confirm-button-text="确定"
                  cancel-button-text="取消"
                  @confirm="handleDeletePassenger(p.passenger_id)"
                >
                  <template #reference>
                    <el-button size="small" link type="danger">
                      <el-icon><Delete /></el-icon> 删除
                    </el-button>
                  </template>
                </el-popconfirm>
                <span v-else class="self-lock-tip">🔒 锁定</span>
              </div>
            </div>

            <div class="p-docs">
              <span class="doc-item">证件: {{ p.id_type || '二代身份证' }}</span>
              <span class="doc-item">{{ maskIdNo(p.id_no) }}</span>
            </div>

            <!-- Passenger In-depth Preferences from preferences_v2 -->
            <div v-if="getPassengerPrefs(p.passenger_id)" class="p-custom-prefs">
              <div class="custom-prefs-title">
                <el-icon><MagicStick /></el-icon>
                <span>专属个性化画像 (L3 行为自动蒸馏学习):</span>
              </div>
              <div class="p-rule-cards">
                <div
                  v-for="(rule, key) in getPassengerPrefs(p.passenger_id)"
                  :key="key"
                  class="p-rule-card"
                >
                  <div class="rule-top-line">
                    <div class="rule-name-box">
                      <span class="rule-name">{{ formatRuleKey(String(key)) }}</span>
                      <span class="rule-raw-key">({{ key }})</span>
                    </div>
                    <el-tag
                      v-if="getRuleConfidence(rule) !== null"
                      size="small"
                      type="success"
                      effect="light"
                      class="conf-badge"
                    >
                      置信度 {{ getRuleConfidence(rule) }}%
                    </el-tag>
                  </div>
                  <div class="rule-body">
                    <span class="rule-val-text">{{ formatRuleValue(String(key), rule) }}</span>
                    <span v-if="formatRuleSource(rule)" class="rule-source-pill">
                      {{ formatRuleSource(rule) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Edit Profile Drawer (人性化表单，彻底告别 JSON) -->
    <el-drawer
      v-model="editDrawerVisible"
      title="编辑用户画像与基础偏好"
      size="540px"
      destroy-on-close
    >
      <div class="drawer-form-content">
        <!-- Section 1: User Context -->
        <div class="drawer-section-card">
          <div class="form-section-title">
            <el-icon><UserFilled /></el-icon>
            <span>👤 助手全局偏好与约束 (User Context - L1)</span>
          </div>

          <el-form label-position="top" class="edit-form">
            <el-form-item label="常驻居住城市 (home_city)">
              <el-input v-model="editForm.homeCity" placeholder="例如：北京 / 上海" clearable />
              <div class="form-item-tip">未指定出发地时，系统默认以常驻城市作为行程起点</div>
            </el-form-item>

            <el-form-item label="默认预算档位 (budget_level)">
              <el-select v-model="editForm.budgetLevel" class="full-width">
                <el-option label="经济优先 (economy) - 追求低价高性价比" value="economy" />
                <el-option label="标准舒适 (standard) - 兼顾舒适与耗时" value="standard" />
                <el-option label="尊享商务 (luxury) - 高品质尊享出行" value="luxury" />
              </el-select>
            </el-form-item>

            <el-form-item label="降价监控灵敏度 (price_drop_ratio)">
              <el-select v-model="editForm.priceDropRatio" class="full-width">
                <el-option label="降价超过 5% 即提醒 (敏锐推荐)" :value="0.05" />
                <el-option label="降价超过 10% 提醒 (标准模式)" :value="0.10" />
                <el-option label="降价超过 20% 提醒 (大幅降价模式)" :value="0.20" />
              </el-select>
            </el-form-item>
          </el-form>
        </div>

        <!-- Section 2: Passenger0 Preferences -->
        <div class="drawer-section-card">
          <div class="form-section-title">
            <el-icon><Guide /></el-icon>
            <span>🚄 本人常用出行习惯 (Passenger0 Preference - L1/L3)</span>
          </div>

          <el-form label-position="top" class="edit-form">
            <el-form-item label="交通工具偏好 (transport)">
              <div class="pref-grid-group">
                <div
                  v-for="opt in transportOptions"
                  :key="opt.value"
                  class="pref-choice-card"
                  :class="{ active: editForm.transport === opt.value }"
                  @click="editForm.transport = opt.value"
                >
                  <div class="choice-icon">{{ opt.icon }}</div>
                  <div class="choice-text">
                    <div class="choice-title">{{ opt.title }}</div>
                    <div class="choice-sub">{{ opt.sub }}</div>
                  </div>
                </div>
              </div>
            </el-form-item>

            <el-form-item label="发车时段偏好 (time_window)">
              <div class="pref-grid-group">
                <div
                  v-for="opt in timeWindowOptions"
                  :key="opt.value"
                  class="pref-choice-card"
                  :class="{ active: editForm.timeWindow === opt.value }"
                  @click="editForm.timeWindow = opt.value"
                >
                  <div class="choice-icon">{{ opt.icon }}</div>
                  <div class="choice-text">
                    <div class="choice-title">{{ opt.title }}</div>
                    <div class="choice-sub">{{ opt.sub }}</div>
                  </div>
                </div>
              </div>
            </el-form-item>

            <el-form-item label="座席位置偏好 (seat)">
              <div class="pref-grid-group">
                <div
                  v-for="opt in seatOptions"
                  :key="opt.value"
                  class="pref-choice-card"
                  :class="{ active: editForm.seat === opt.value }"
                  @click="editForm.seat = opt.value"
                >
                  <div class="choice-icon">{{ opt.icon }}</div>
                  <div class="choice-text">
                    <div class="choice-title">{{ opt.title }}</div>
                    <div class="choice-sub">{{ opt.sub }}</div>
                  </div>
                </div>
              </div>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <template #footer>
        <div class="drawer-footer">
          <el-button @click="editDrawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="memoryStore.isSaving" @click="saveEdit">
            保存偏好配置
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 乘车人新增/编辑弹窗 -->
    <PassengerModal
      v-model="showPassengerModal"
      :passenger-data="activePassenger"
      @saved="handlePassengerSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, User, UserFilled, MagicStick, Plus, Delete, Guide } from '@element-plus/icons-vue'
import { useMemoryStore } from '@/stores/memory'
import { memoryApi } from '@/api/memory'
import type { UserProfile } from '@/types/memory'
import PassengerModal from '@/components/chat/PassengerModal.vue'

const props = defineProps<{
  profile: UserProfile | null
}>()

const memoryStore = useMemoryStore()
const editDrawerVisible = ref(false)
const showPassengerModal = ref(false)
const activePassenger = ref<any>(null)

const editForm = ref({
  homeCity: '',
  budgetLevel: 'standard',
  priceDropRatio: 0.05,
  transport: 'none',
  timeWindow: 'none',
  seat: 'none',
})

const transportOptions = [
  { value: 'train', icon: '🚄', title: '高铁优先', sub: '动车/高铁出行' },
  { value: 'flight', icon: '✈️', title: '机票优先', sub: '航班快速直达' },
  { value: 'none', icon: '⚖️', title: '综合比选', sub: '智能择优推荐' },
]

const timeWindowOptions = [
  { value: 'morning', icon: '🌅', title: '清晨早班', sub: '05:00 - 08:00' },
  { value: 'afternoon', icon: '☀️', title: '日间适中', sub: '09:00 - 18:00' },
  { value: 'none', icon: '🕒', title: '全天不限', sub: '全时段智能比选' },
]

const seatOptions = [
  { value: 'window', icon: '🪟', title: '靠窗优先', sub: '沿途视野景观佳' },
  { value: 'aisle', icon: '🚶', title: '靠过道', sub: '出入走动更自如' },
  { value: 'none', icon: '💺', title: '随意均可', sub: '无特殊位置要求' },
]

const SYSTEM_COUNTER_KEYS = ['positive_feedback', 'negative_feedback', 'switch_count']

const displayPreferences = computed(() => {
  const res: Record<string, any> = {}
  // 1. User L1 / L3 偏好（如降价监控灵敏度）
  const userV2 = props.profile?.preferences_v2?.user || {}
  if (userV2.price_drop_ratio?.value !== undefined) {
    res['price_drop_ratio'] = userV2.price_drop_ratio
  }
  // 2. 本人（Passenger0）专属出行偏好
  const selfV2 = props.profile?.preferences_v2?.passengers?.['0'] || {}
  for (const [k, v] of Object.entries(selfV2)) {
    res[k] = v
  }
  // 3. 兜底旧版 flat 偏好（排除系统内部打点计数器）
  if (props.profile?.preferences) {
    for (const [k, v] of Object.entries(props.profile.preferences)) {
      if (!SYSTEM_COUNTER_KEYS.includes(k) && !res[k]) {
        res[k] = v
      }
    }
  }
  return res
})

const feedbackStats = computed(() => {
  const p = props.profile?.preferences || {}
  return {
    positive: Number(p.positive_feedback || 0),
    negative: Number(p.negative_feedback || 0),
    switches: Number(p.switch_count || 0),
  }
})

const hasFeedback = computed(() => {
  return feedbackStats.value.positive > 0 || feedbackStats.value.negative > 0 || feedbackStats.value.switches > 0
})

function formatRuleKey(key: string): string {
  const map: Record<string, string> = {
    transport: '交通工具偏好',
    preferred_transport: '交通工具偏好',
    time_window: '出行时段偏好',
    departure_time: '发车时段偏好',
    seat: '座席位置偏好',
    seat_preference: '座席位置偏好',
    price_sensitivity: '价格敏感度',
    price_drop_ratio: '降价提醒灵敏度',
    speed_preference: '出行速度偏好',
    avoid_early_morning: '避开清晨早班',
  }
  return map[key] || key
}

function formatRuleValue(key: string, rule: any): string {
  const val = (rule && typeof rule === 'object' && rule.value !== undefined) ? rule.value : rule
  if (key === 'transport' || key === 'preferred_transport') {
    if (val === 'train') return '🚄 高铁 / 火车优先'
    if (val === 'flight') return '✈️ 机票 / 航空优先'
  }
  if (key === 'time_window') {
    if (val === 'morning') return '🌅 早间时段 (05:00-08:00)'
    if (val === 'afternoon') return '☀️ 日间适中 (09:00-18:00)'
    if (val === 'night') return '🌙 晚间时段'
  }
  if (key === 'seat' || key === 'seat_preference') {
    if (val === 'window') return '🪟 靠窗优先'
    if (val === 'aisle') return '🚶 靠过道优先'
  }
  if (typeof val === 'number') {
    if (val === 0.05) return '降价 > 5% 及时提醒 (敏锐推荐)'
    if (val === 0.1) return '降价 > 10% 提醒'
    if (val === 0.2) return '降价 > 20% 提醒'
  }
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatRuleSource(rule: any): string {
  if (!rule || typeof rule !== 'object') return ''
  const src = rule.source
  if (src === 'distilled') return '🤖 历史行程自动沉淀'
  if (src === 'explicit') return '👤 用户手动配置'
  if (src === 'inferred') return '💡 规则推断'
  return src ? `来源: ${src}` : ''
}

function getRuleConfidence(rule: any): number | null {
  if (!rule || typeof rule !== 'object') return null
  if (typeof rule.confidence === 'number') {
    return Math.round(rule.confidence * 100)
  }
  return null
}

function openEditDrawer() {
  if (props.profile) {
    editForm.value.homeCity = props.profile.home_city || ''
    editForm.value.budgetLevel = props.profile.budget_level || 'standard'

    const userV2 = props.profile.preferences_v2?.user || {}
    if (userV2.price_drop_ratio?.value !== undefined) {
      editForm.value.priceDropRatio = Number(userV2.price_drop_ratio.value)
    } else {
      editForm.value.priceDropRatio = 0.05
    }

    const selfV2 = props.profile.preferences_v2?.passengers?.['0'] || {}
    editForm.value.transport = selfV2.transport?.value || 'none'
    editForm.value.timeWindow = selfV2.time_window?.value || 'none'
    editForm.value.seat = selfV2.seat?.value || 'none'
  }
  editDrawerVisible.value = true
}

async function saveEdit() {
  try {
    const newPrefsV2: Record<string, any> = {
      user: {
        ...(props.profile?.preferences_v2?.user || {}),
        price_drop_ratio: {
          value: editForm.value.priceDropRatio,
          source: 'explicit',
          confidence: 1.0,
        },
      },
      passengers: {
        ...(props.profile?.preferences_v2?.passengers || {}),
        '0': {
          ...(props.profile?.preferences_v2?.passengers?.['0'] || {}),
        },
      },
    }

    if (editForm.value.transport !== 'none') {
      newPrefsV2.passengers['0'].transport = {
        value: editForm.value.transport,
        source: 'explicit',
        confidence: 1.0,
      }
    } else {
      delete newPrefsV2.passengers['0'].transport
    }

    if (editForm.value.timeWindow !== 'none') {
      newPrefsV2.passengers['0'].time_window = {
        value: editForm.value.timeWindow,
        source: 'explicit',
        confidence: 1.0,
      }
    } else {
      delete newPrefsV2.passengers['0'].time_window
    }

    if (editForm.value.seat !== 'none') {
      newPrefsV2.passengers['0'].seat = {
        value: editForm.value.seat,
        source: 'explicit',
        confidence: 1.0,
      }
    } else {
      delete newPrefsV2.passengers['0'].seat
    }

    await memoryStore.updateProfile({
      home_city: editForm.value.homeCity,
      budget_level: editForm.value.budgetLevel,
      preferences_v2: newPrefsV2,
    })
    ElMessage.success('用户画像与出行偏好已成功保存！')
    editDrawerVisible.value = false
  } catch (err: any) {
    ElMessage.error(err?.message || '保存失败')
  }
}

function openAddPassengerModal() {
  activePassenger.value = null
  showPassengerModal.value = true
}

function openEditPassengerModal(p: any) {
  activePassenger.value = p
  showPassengerModal.value = true
}

async function handleDeletePassenger(pid: string) {
  try {
    const updated = await memoryApi.deletePassenger(pid)
    memoryStore.profile = updated
    ElMessage.success('已从同行乘客簿中删除该乘车人！')
  } catch (err: any) {
    console.error('Delete passenger failed:', err)
    ElMessage.error(err?.response?.data?.detail || '删除失败，请重试')
  }
}

function handlePassengerSaved() {
  // Modal automatically re-syncs memoryStore.profile
}

function getPassengerPrefs(pid: string): Record<string, any> | null {
  const v2 = props.profile?.preferences_v2?.passengers
  if (v2 && v2[pid] && Object.keys(v2[pid]).length > 0) {
    return v2[pid]
  }
  return null
}

function formatKey(key: string): string {
  return formatRuleKey(key)
}

function formatVal(val: any): string {
  return formatRuleValue('', val)
}

function maskIdNo(idNo?: string): string {
  if (!idNo) return '已实名备案'
  if (idNo.length < 8) return idNo
  return `${idNo.slice(0, 4)} **** **** ${idNo.slice(-4)}`
}
</script>

<style scoped>
.profile-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.profile-header {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.user-meta-summary {
  display: flex;
  align-items: center;
  gap: 14px;
}

.user-avatar-badge {
  font-size: 24px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: #eff6ff;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #bfdbfe;
}

.user-meta-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.user-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.city-tag, .budget-tag {
  font-size: 11px;
  background: #f1f5f9;
  color: #475569;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.budget-tag {
  background: #e0f2fe;
  color: #0369a1;
}

.user-sub {
  font-size: 12px;
  color: #64748b;
}

.profile-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.pref-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
  margin-bottom: 14px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.card-tag {
  font-size: 11px;
  background: #f1f5f9;
  color: #64748b;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.empty-pref {
  padding: 24px 0;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
}

.empty-hint {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 4px;
}

.empty-sub {
  font-size: 11px;
  color: #94a3b8;
}

.feedback-stats-footer {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px dashed #e2e8f0;
}

.stats-title {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 6px;
  display: block;
}

.stats-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.stat-pill {
  font-weight: 500;
}

.pref-items-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pref-item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
}

.pref-key-box {
  display: flex;
  flex-direction: column;
}

.pref-key {
  font-size: 12.5px;
  font-weight: 600;
  color: #1e293b;
}

.pref-key-raw {
  font-family: monospace;
  font-size: 10.5px;
  color: #94a3b8;
}

.pref-val-box {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  padding: 3px 10px;
  border-radius: 6px;
}

.pref-val {
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: #2563eb;
}

.passenger-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.passenger-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
}

.passenger-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.p-name-role {
  display: flex;
  align-items: center;
  gap: 8px;
}

.p-name {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.p-role {
  font-size: 11px;
  background: #e2e8f0;
  color: #475569;
  padding: 1px 6px;
  border-radius: 4px;
}

.p-id {
  font-family: monospace;
  font-size: 11px;
  color: #94a3b8;
}

.p-docs {
  display: flex;
  gap: 12px;
  font-size: 11.5px;
  color: #64748b;
  margin-bottom: 6px;
}

.p-custom-prefs {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
}

.custom-prefs-title {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.p-rule-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 6px;
}

.p-rule-card {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 8px 12px;
}

.rule-top-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.rule-name-box {
  display: flex;
  align-items: center;
  gap: 4px;
}

.rule-name {
  font-size: 12px;
  font-weight: 700;
  color: #1e40af;
}

.rule-raw-key {
  font-family: monospace;
  font-size: 10.5px;
  color: #60a5fa;
}

.conf-badge {
  font-weight: 600;
}

.rule-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.rule-val-text {
  font-size: 12.5px;
  font-weight: 600;
  color: #0f172a;
}

.rule-source-pill {
  font-size: 10.5px;
  color: #64748b;
  background: #ffffff;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
}

.full-width {
  width: 100%;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.p-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.p-id-pill {
  font-size: 11px;
  color: #94a3b8;
  font-family: monospace;
}

.self-lock-tip {
  font-size: 11px;
  color: #94a3b8;
}

.drawer-form-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 2px 20px 2px;
}

.drawer-section-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 18px;
}

.drawer-section-card .edit-form :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

.form-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
}

.form-item-tip {
  font-size: 11.5px;
  color: #64748b;
  margin-top: 4px;
  line-height: 1.4;
}

/* 3-Column Grid Choice Cards */
.pref-grid-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  width: 100%;
}

.pref-choice-card {
  background: #ffffff;
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 6px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  user-select: none;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}

.pref-choice-card:hover {
  background: #ffffff;
  border-color: #93c5fd;
  transform: translateY(-1px);
  box-shadow: 0 3px 8px rgba(37, 99, 235, 0.08);
}

.pref-choice-card.active {
  background: #eff6ff;
  border-color: #2563eb;
  box-shadow: 0 0 0 1px #2563eb;
}

.choice-icon {
  font-size: 20px;
  line-height: 1.2;
}

.choice-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.choice-title {
  font-size: 12.5px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.3;
}

.pref-choice-card.active .choice-title {
  color: #1d4ed8;
}

.choice-sub {
  font-size: 10px;
  color: #94a3b8;
  line-height: 1.2;
}

.pref-choice-card.active .choice-sub {
  color: #3b82f6;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
