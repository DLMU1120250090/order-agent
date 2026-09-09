<template>
  <div class="orders-workspace">
    <!-- Topbar -->
    <header class="orders-topbar">
      <div class="topbar-left">
        <div class="page-title">
          <el-icon><Tickets /></el-icon>
          <span>订单与履约中心 (Order & Fulfillment Center)</span>
        </div>

        <!-- Status Filter Chips -->
        <div class="status-chips">
          <button
            v-for="s in STATUS_TABS"
            :key="s.key"
            type="button"
            class="status-chip"
            :class="{ active: orderStore.statusFilter === s.key }"
            @click="orderStore.statusFilter = s.key"
          >
            {{ s.label }}
          </button>
        </div>
      </div>

      <div class="topbar-right">
        <el-button
          size="small"
          plain
          :loading="orderStore.isLoading"
          @click="orderStore.fetchOrders"
        >
          <el-icon><Refresh /></el-icon>
          刷新订单
        </el-button>
      </div>
    </header>

    <!-- Main Content Area -->
    <main v-loading="orderStore.isLoading" class="orders-main-pane">
      <div class="orders-container">
        <!-- Empty State -->
        <div v-if="orderStore.filteredOrders.length === 0" class="empty-card">
          <el-empty description="暂无符合条件的订单记录喵~" />
          <router-link to="/travel/chat">
            <el-button type="primary">前往对话区规划并预订行程</el-button>
          </router-link>
        </div>

        <!-- Orders Cards List -->
        <div v-else class="orders-list">
          <div
            v-for="order in orderStore.filteredOrders"
            :key="order.orderNo || (order as any).order_no"
            class="order-card"
          >
            <!-- Card Header -->
            <div class="card-head">
              <div class="head-left">
                <span class="order-no-badge">单号: {{ getOrderNo(order) }}</span>
                <span class="supplier-tag">{{ (order as any).supplier || '12306 官方' }}</span>
              </div>
              <div class="head-right">
                <span class="status-pill" :class="statusClass(order.status)">
                  {{ statusText(order.status) }}
                </span>
              </div>
            </div>

            <!-- Visual State Machine Stepper -->
            <div class="order-stepper">
              <div
                class="step-item"
                :class="stepClass(order.status, 1)"
              >
                <div class="step-circle">1</div>
                <span class="step-label">已创建</span>
              </div>
              <div class="step-connector" :class="{ filled: stepFilled(order.status, 2) }"></div>

              <div
                class="step-item"
                :class="stepClass(order.status, 2)"
              >
                <div class="step-circle">2</div>
                <span class="step-label">已锁座</span>
              </div>
              <div class="step-connector" :class="{ filled: stepFilled(order.status, 3) }"></div>

              <div
                class="step-item"
                :class="stepClass(order.status, 3)"
              >
                <div class="step-circle">3</div>
                <span class="step-label">已支付</span>
              </div>
              <div class="step-connector" :class="{ filled: stepFilled(order.status, 4) }"></div>

              <div
                class="step-item"
                :class="stepClass(order.status, 4)"
              >
                <div class="step-circle">{{ getStep4Icon(order.status) }}</div>
                <span class="step-label">{{ getStep4Label(order.status) }}</span>
                <span class="step-sublabel">{{ getStep4Subtitle(order.status) }}</span>
              </div>
            </div>

            <!-- Route & Legs Content (Professional Ticket Board) -->
            <div class="card-body-content">
              <div class="route-banner">
                <!-- Departure Column -->
                <div class="route-col departure-col">
                  <div class="time-main">{{ getDepartTime(order) }}</div>
                  <div class="city-main">{{ getOrigin(order) }}</div>
                  <div class="station-sub" v-if="getOriginStation(order)">
                    {{ getOriginStation(order) }}
                  </div>
                </div>

                <!-- Center Journey Route -->
                <div class="route-center-flow">
                  <div class="trip-date-pill" v-if="getTripDate(order)">
                    <el-icon><Calendar /></el-icon>
                    <span>{{ getTripDate(order) }} 出发</span>
                  </div>

                  <div class="vehicle-flight-badge">
                    <span class="v-icon">{{ isFlight(order) ? '✈️' : '🚄' }}</span>
                    <span class="v-code">{{ getVehicleNo(order) }}</span>
                    <span class="v-seat-tag" v-if="getSeatType(order)">{{ getSeatType(order) }}</span>
                  </div>

                  <div class="arrow-visual-track">
                    <div class="track-line"></div>
                    <div class="track-arrow">➔</div>
                  </div>

                  <div class="duration-hint" v-if="getDuration(order)">
                    耗时约 {{ getDuration(order) }}
                  </div>
                </div>

                <!-- Arrival Column -->
                <div class="route-col arrival-col">
                  <div class="time-main">{{ getArriveTime(order) }}</div>
                  <div class="city-main">{{ getDestination(order) }}</div>
                  <div class="station-sub" v-if="getDestinationStation(order)">
                    {{ getDestinationStation(order) }}
                  </div>
                </div>

                <!-- Price Box -->
                <div class="price-box">
                  <span class="currency">¥</span>
                  <span class="amount">{{ order.totalPrice || (order as any).price || 0 }}</span>
                </div>
              </div>

              <!-- Passengers and Leg Details -->
              <div class="details-row">
                <div class="passengers-box">
                  <span class="lbl">出行人:</span>
                  <div class="p-tags">
                    <span
                      v-for="(p, pIdx) in getPassengers(order)"
                      :key="pIdx"
                      class="p-chip"
                    >
                      👤 {{ typeof p === 'string' ? p : p.name || p.passenger_id || `出行人 ${pIdx + 1}` }}
                    </span>
                  </div>
                </div>

                <div class="seat-info-box">
                  <span class="lbl">行程日期:</span>
                  <span class="date-val">{{ getTripDate(order) }}</span>
                  <span class="lbl" style="margin-left: 12px;">席别:</span>
                  <span class="seat-val">{{ getSeatType(order) }}</span>
                </div>
              </div>
            </div>

            <!-- Card Bottom Action Bar -->
            <div class="card-footer">
              <div class="footer-left">
                <span class="create-time">创建时间: {{ formatDate(order.createdAt || (order as any).created_at) }}</span>
              </div>

              <div class="footer-right">
                <!-- If LOCKED / Unpaid -> Pay button -->
                <a
                  v-if="order.status === 'LOCKED' || (order as any).pending === 'PAYMENT'"
                  :href="`/mock/checkout.html?order_no=${getOrderNo(order)}`"
                  target="_blank"
                  class="pay-btn-link"
                >
                  <el-button type="success" size="small">
                    <el-icon><Money /></el-icon>
                    前往收银台支付
                  </el-button>
                </a>

                <!-- Change Ticket Button (Only for PAID) -->
                <el-button
                  v-if="order.status === 'PAID'"
                  size="small"
                  plain
                  @click="handleChangeClick(order)"
                >
                  <el-icon><Switch /></el-icon>
                  申请改签
                </el-button>

                <!-- Refund Button (Only for PAID) -->
                <el-button
                  v-if="order.status === 'PAID'"
                  size="small"
                  plain
                  type="danger"
                  @click="handleRefundClick(order)"
                >
                  <el-icon><CloseBold /></el-icon>
                  申请退票
                </el-button>

                <!-- Mutex Badges for non-PAID -->
                <el-tag
                  v-else-if="order.status === 'REFUNDED'"
                  type="info"
                  effect="plain"
                  class="status-action-tag"
                >
                  已办理退票（已完成退款）
                </el-tag>
                <el-tag
                  v-else-if="order.status === 'REFUNDING'"
                  type="warning"
                  effect="plain"
                  class="status-action-tag"
                >
                  <el-icon class="is-loading"><Loading /></el-icon>
                  退票处理中…
                </el-tag>
                <el-tag
                  v-else-if="order.status === 'CHANGED'"
                  type="success"
                  effect="plain"
                  class="status-action-tag"
                >
                  已办理改签（不可再次改签/退票）
                </el-tag>
                <el-tag
                  v-else-if="order.status === 'CHANGING'"
                  type="warning"
                  effect="plain"
                  class="status-action-tag"
                >
                  <el-icon class="is-loading"><Loading /></el-icon>
                  改签处理中…
                </el-tag>
                <el-tag
                  v-else-if="order.status === 'COMPLETED'"
                  type="success"
                  effect="plain"
                  class="status-action-tag"
                >
                  <el-icon><Check /></el-icon>
                  行程已圆满完成 (已出行)
                </el-tag>
                <el-tag
                  v-else-if="order.status === 'CANCELLED'"
                  type="info"
                  effect="plain"
                  class="status-action-tag"
                >
                  订单已取消
                </el-tag>

                <!-- Checklist Button -->
                <el-button
                  size="small"
                  type="primary"
                  plain
                  @click="openChecklist(order)"
                >
                  <el-icon><List /></el-icon>
                  出行清单 (Checklist)
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Checklist Dialog -->
    <el-dialog
      v-model="checklistVisible"
      title="🧳 智能出行准备备忘清单 (Checklist)"
      width="560px"
      destroy-on-close
    >
      <div class="checklist-modal-body">
        <div class="checklist-dest-banner">
          <div class="banner-icon">🌦️</div>
          <div class="banner-info">
            <span class="b-dest">目的地: {{ currentChecklistDest }}</span>
            <span class="b-tip">Agent 已自动根据目的地气候与交通类型为您生成贴心行前备忘</span>
          </div>
        </div>

        <div class="checklist-groups">
          <div class="check-group">
            <div class="group-title">🪪 随身证件与乘车凭证</div>
            <ul class="group-items">
              <li>身份证件原件（如二代身份证、港澳通行证或护照）</li>
              <li>车票订单凭证（已完成电子验票，直接刷证乘车）</li>
              <li>适量现金或备用支付手机</li>
            </ul>
          </div>

          <div class="check-group">
            <div class="group-title">📱 电子设备与移动电源</div>
            <ul class="group-items">
              <li>手机充电线与具备 3C 认证的移动电源（高铁可直接车厢充电）</li>
              <li>降噪耳机（旅途休憩首选）</li>
            </ul>
          </div>

          <div class="check-group">
            <div class="group-title">👔 衣物与常备健康小包</div>
            <ul class="group-items">
              <li>建议随身携带薄外套一件（车厢内空调温度较低）</li>
              <li>便携纸巾、消毒湿巾与晴雨两用伞</li>
            </ul>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="checklistVisible = false">关闭</el-button>
          <el-button type="primary" @click="exportChecklist">
            <el-icon><DocumentCopy /></el-icon>
            复制清单文本
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Calendar, Loading, Money, Switch, CloseBold, List, DocumentCopy, Check } from '@element-plus/icons-vue'
import { useOrderStore } from '@/stores/order'
import type { TravelOrder } from '@/types/order'

const router = useRouter()
const orderStore = useOrderStore()

const STATUS_TABS = [
  { key: 'ALL', label: '全部订单' },
  { key: 'LOCKED', label: '待支付 (已锁座)' },
  { key: 'PAID', label: '已支付 (待出行)' },
  { key: 'COMPLETED', label: '已出行' },
  { key: 'CHANGED', label: '已改签' },
  { key: 'REFUNDED', label: '已退票' },
]

const checklistVisible = ref(false)
const currentChecklistDest = ref('目的地')

onMounted(async () => {
  await orderStore.fetchOrders()
})

function getOrderNo(order: any): string {
  return order.orderNo || order.order_no || 'TRV-ORDER'
}

function isFlight(order: any): boolean {
  const type = order.type || (order.legs && order.legs[0]?.mode) || (order.legs && order.legs[0]?.type) || ''
  return String(type).toUpperCase().includes('FLIGHT')
}

function getOrigin(order: any): string {
  if (order.legs && order.legs.length > 0) {
    const leg = order.legs[0]
    return leg.from_city || leg.origin || (leg.from_station ? leg.from_station.replace(/站|机场/g, '') : '北京')
  }
  return '北京'
}

function getOriginStation(order: any): string {
  if (order.legs && order.legs.length > 0) {
    const leg = order.legs[0]
    return leg.from_station || ''
  }
  return ''
}

function getDestination(order: any): string {
  if (order.legs && order.legs.length > 0) {
    const leg = order.legs[order.legs.length - 1]
    return leg.to_city || leg.destination || (leg.to_station ? leg.to_station.replace(/站|机场/g, '') : '上海')
  }
  return '上海'
}

function getDestinationStation(order: any): string {
  if (order.legs && order.legs.length > 0) {
    const leg = order.legs[order.legs.length - 1]
    return leg.to_station || ''
  }
  return ''
}

function getDepartTime(order: any): string {
  if (order.legs && order.legs.length > 0) {
    return order.legs[0].depart || '09:00'
  }
  return '09:00'
}

function getArriveTime(order: any): string {
  if (order.legs && order.legs.length > 0) {
    return order.legs[order.legs.length - 1].arrive || '13:00'
  }
  return '13:00'
}

function getTripDate(order: any): string {
  const raw = order.tripDate || order.trip_date || (order.createdAt || order.created_at)
  if (!raw) return '2026-09-09'
  return String(raw).split(' ')[0].split('T')[0]
}

function getVehicleNo(order: any): string {
  if (order.legs && order.legs.length > 0) {
    return order.legs[0].vehicle_no || order.legs[0].train_no || (isFlight(order) ? 'CA1234' : 'G1234')
  }
  return isFlight(order) ? 'CA1234' : 'G1234'
}

function getSeatType(order: any): string {
  if (order.legs && order.legs.length > 0) {
    return order.legs[0].seat || order.legs[0].seat_type || (isFlight(order) ? '经济舱' : '二等座')
  }
  return isFlight(order) ? '经济舱' : '二等座'
}

function getDuration(order: any): string {
  if (order.legs && order.legs.length > 0) {
    const dep = order.legs[0].depart
    const arr = order.legs[order.legs.length - 1].arrive
    if (dep && arr && dep.includes(':') && arr.includes(':')) {
      const [dh, dm] = dep.split(':').map(Number)
      const [ah, am] = arr.split(':').map(Number)
      let diff = (ah * 60 + am) - (dh * 60 + dm)
      if (diff < 0) diff += 24 * 60
      const h = Math.floor(diff / 60)
      const m = diff % 60
      return m > 0 ? `${h}h${m}m` : `${h}h`
    }
  }
  return ''
}

function getPassengers(order: any): any[] {
  if (Array.isArray(order.passengers) && order.passengers.length > 0) {
    return order.passengers
  }
  return ['本人 (已实名)']
}

function getStep4Label(status?: string): string {
  const s = (status || '').toUpperCase()
  if (s === 'REFUNDED') return '已退票'
  if (s === 'REFUNDING') return '退票中'
  if (s === 'CHANGED') return '已改签'
  if (s === 'CHANGING') return '改签中'
  if (s === 'COMPLETED') return '已出行'
  return '待出行'
}

function getStep4Subtitle(status?: string): string {
  const s = (status || '').toUpperCase()
  if (s === 'REFUNDED') return '款项原路退回'
  if (s === 'REFUNDING') return '正在办理退款'
  if (s === 'CHANGED') return '新席位已生效'
  if (s === 'CHANGING') return '正在换签席位'
  if (s === 'COMPLETED') return '行程圆满结束'
  return '凭有效证件乘车'
}

function getStep4Icon(status?: string): string {
  const s = (status || '').toUpperCase()
  if (s === 'REFUNDED') return '✕'
  if (s === 'REFUNDING') return '⋯'
  if (s === 'CHANGED') return '✓'
  if (s === 'CHANGING') return '⋯'
  if (s === 'COMPLETED') return '✓'
  return '4'
}

function statusText(status?: string): string {
  switch ((status || '').toUpperCase()) {
    case 'CREATED': return '已创建'
    case 'LOCKED': return '已锁座 · 待支付'
    case 'PAID': return '已支付 · 待出行'
    case 'REFUNDING': return '退票中'
    case 'REFUNDED': return '已全额退票'
    case 'CHANGING': return '改签中'
    case 'CHANGED': return '已改签'
    case 'COMPLETED': return '已出行'
    case 'CANCELLED': return '已取消'
    default: return status || '进行中'
  }
}

function statusClass(status?: string): string {
  switch ((status || '').toUpperCase()) {
    case 'LOCKED': return 'status-locked'
    case 'PAID': return 'status-paid'
    case 'COMPLETED': return 'status-completed'
    case 'REFUNDING': return 'status-refunding'
    case 'REFUNDED': return 'status-refunded'
    case 'CHANGING': return 'status-changing'
    case 'CHANGED': return 'status-changed'
    case 'CANCELLED': return 'status-cancelled'
    default: return 'status-default'
  }
}

function stepClass(status: string | undefined, stepNo: number): string {
  const s = (status || '').toUpperCase()
  if (stepNo === 1) return 'finished'
  if (stepNo === 2) {
    if (s === 'CREATED') return 'active'
    return 'finished'
  }
  if (stepNo === 3) {
    if (s === 'LOCKED') return 'active'
    if (['PAID', 'CHANGED', 'CHANGING', 'REFUNDED', 'REFUNDING', 'COMPLETED'].includes(s)) return 'finished'
    return 'pending'
  }
  if (stepNo === 4) {
    if (s === 'REFUNDED') return 'finished-refunded'
    if (s === 'REFUNDING') return 'active-refunding'
    if (s === 'CHANGED') return 'finished-changed'
    if (s === 'CHANGING') return 'active-changing'
    if (s === 'COMPLETED') return 'finished'
    if (s === 'PAID') return 'pending-trip'
    return 'pending'
  }
  return 'pending'
}

function stepFilled(status: string | undefined, stepNo: number): boolean {
  const s = (status || '').toUpperCase()
  if (stepNo === 2) return true
  if (stepNo === 3) return ['PAID', 'CHANGED', 'CHANGING', 'REFUNDED', 'REFUNDING', 'COMPLETED'].includes(s)
  if (stepNo === 4) return ['REFUNDED', 'REFUNDING', 'CHANGED', 'CHANGING', 'COMPLETED'].includes(s)
  return false
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '-'
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `${y}-${m}-${day} ${hh}:${mm}:${ss}`
  } catch {
    return dateStr
  }
}

async function handleRefundClick(order: any) {
  const orderNo = getOrderNo(order)
  const origin = getOrigin(order)
  const dest = getDestination(order)
  const price = order.totalPrice || (order as any).price || 0

  try {
    await ElMessageBox.confirm(
      `确定要申请退掉订单【${orderNo}】（${origin} ➔ ${dest} · ¥${price}）吗？\n\n确认后将自动为您转入规划助手发起退票流转喵~`,
      '⚠️ 确认申请退票',
      {
        confirmButtonText: '确认退票',
        cancelButtonText: '暂不退票',
        confirmButtonClass: 'el-button--danger',
        type: 'warning',
        distinguishCancelAndClose: true,
      }
    )
    goToChatWithAction(`帮我退掉订单 ${orderNo}`)
  } catch {
    // User cancelled
  }
}

async function handleChangeClick(order: any) {
  const orderNo = getOrderNo(order)
  const origin = getOrigin(order)
  const dest = getDestination(order)

  try {
    await ElMessageBox.confirm(
      `确定要申请改签订单【${orderNo}】（${origin} ➔ ${dest}）吗？\n\n确认后将自动为您转入规划助手比选改签方案喵~`,
      '🔁 确认申请改签',
      {
        confirmButtonText: '申请改签',
        cancelButtonText: '取消',
        type: 'info',
        distinguishCancelAndClose: true,
      }
    )
    goToChatWithAction(`我想改签订单 ${orderNo}`)
  } catch {
    // User cancelled
  }
}

function goToChatWithAction(prompt: string) {
  router.push({
    path: '/travel/chat',
    query: { prompt },
  })
}

function openChecklist(order: any) {
  currentChecklistDest.value = getDestination(order)
  checklistVisible.value = true
}

async function exportChecklist() {
  const text = `【出行备忘清单 - ${currentChecklistDest.value}】\n1. 身份证件原件及车票订单\n2. 手机充电线、移动电源\n3. 车厢便携薄外套、晴雨伞\n4. 常用药物与洗漱包\n愿您旅途平安愉快！`
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('出行清单已成功复制到剪贴板！')
    checklistVisible.value = false
  } catch {
    ElMessage.info(text)
  }
}
</script>

<style scoped>
.orders-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: #f8fafc;
  overflow: hidden;
}

.orders-topbar {
  height: 52px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.status-chips {
  display: flex;
  gap: 4px;
}

.status-chip {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11.5px;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s ease;
}

.status-chip:hover {
  background: #e2e8f0;
}

.status-chip.active {
  background: #2563eb;
  color: #ffffff;
  border-color: #2563eb;
  font-weight: 600;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.orders-main-pane {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

.orders-container {
  max-width: 900px;
  margin: 0 auto;
}

.empty-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 60px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.orders-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.order-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.order-no-badge {
  font-family: monospace;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.supplier-tag {
  font-size: 11px;
  background: #f1f5f9;
  color: #475569;
  padding: 1px 6px;
  border-radius: 4px;
}

.status-pill {
  font-size: 11.5px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 9999px;
}

.status-locked { background: #dbeafe; color: #1d4ed8; }
.status-paid { background: #dcfce7; color: #15803d; }
.status-completed { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.status-refunding { background: #fef3c7; color: #b45309; }
.status-refunded { background: #fee2e2; color: #b91c1c; }
.status-changing { background: #fef3c7; color: #b45309; }
.status-changed { background: #e0f2fe; color: #0369a1; }
.status-cancelled { background: #f1f5f9; color: #64748b; }
.status-default { background: #f1f5f9; color: #64748b; }

.status-action-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  height: 28px;
}

/* Stepper */
.order-stepper {
  display: flex;
  align-items: center;
  background: #f8fafc;
  padding: 10px 16px;
  border-radius: 8px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #94a3b8;
}

.step-sublabel {
  font-size: 10.5px;
  color: #94a3b8;
  font-weight: normal;
  margin-left: 2px;
}

@media (max-width: 640px) {
  .step-sublabel {
    display: none;
  }
}

.step-circle {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}

.step-item.finished .step-circle {
  background: #22c55e;
  color: #ffffff;
}

.step-item.finished .step-label {
  color: #166534;
  font-weight: 600;
}

.step-item.active .step-circle {
  background: #2563eb;
  color: #ffffff;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2);
}

.step-item.active .step-label {
  color: #1d4ed8;
  font-weight: 700;
}

.step-item.finished-refunded .step-circle {
  background: #ef4444;
  color: #ffffff;
}

.step-item.finished-refunded .step-label {
  color: #b91c1c;
  font-weight: 700;
}

.step-item.active-refunding .step-circle {
  background: #f59e0b;
  color: #ffffff;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.2);
}

.step-item.active-refunding .step-label {
  color: #b45309;
  font-weight: 700;
}

.step-item.finished-changed .step-circle {
  background: #0ea5e9;
  color: #ffffff;
}

.step-item.finished-changed .step-label {
  color: #0369a1;
  font-weight: 700;
}

.step-item.active-changing .step-circle {
  background: #f59e0b;
  color: #ffffff;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.2);
}

.step-item.active-changing .step-label {
  color: #b45309;
  font-weight: 700;
}

.step-item.pending-trip .step-circle {
  background: #e2e8f0;
  color: #64748b;
}

.step-item.pending-trip .step-label {
  color: #475569;
  font-weight: 600;
}

.step-connector {
  flex: 1;
  height: 2px;
  background: #e2e8f0;
  margin: 0 10px;
}

.step-connector.filled {
  background: #86efac;
}

/* Body Content */
.card-body-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.route-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.route-col {
  display: flex;
  flex-direction: column;
  min-width: 100px;
}

.departure-col {
  text-align: left;
  align-items: flex-start;
}

.arrival-col {
  text-align: right;
  align-items: flex-end;
}

.time-main {
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.1;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

.city-main {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  margin-top: 4px;
}

.station-sub {
  font-size: 11.5px;
  color: #64748b;
  margin-top: 2px;
}

.route-center-flow {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 16px;
  max-width: 260px;
}

.trip-date-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 12px;
  margin-bottom: 4px;
}

.vehicle-flight-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.v-icon {
  font-size: 13px;
}

.v-code {
  font-family: monospace;
  font-weight: 700;
  color: #2563eb;
  font-size: 12px;
}

.v-seat-tag {
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  color: #475569;
  font-size: 10.5px;
  padding: 0 5px;
  border-radius: 4px;
}

.arrow-visual-track {
  width: 100%;
  display: flex;
  align-items: center;
  position: relative;
  margin: 4px 0;
}

.track-line {
  flex: 1;
  height: 2px;
  background: #94a3b8;
}

.track-arrow {
  color: #64748b;
  font-size: 11px;
  margin-left: -2px;
}

.duration-hint {
  font-size: 11px;
  color: #94a3b8;
}

.price-box {
  display: flex;
  align-items: baseline;
  color: #ea580c;
  min-width: 80px;
  justify-content: flex-end;
}

.currency {
  font-size: 13px;
  font-weight: 700;
}

.amount {
  font-size: 22px;
  font-weight: 800;
}

.details-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  padding: 0 4px;
}

.passengers-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lbl {
  color: #94a3b8;
}

.p-tags {
  display: flex;
  gap: 6px;
}

.p-chip {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 1px 7px;
  border-radius: 4px;
  color: #334155;
  font-size: 11.5px;
}

.seat-info-box {
  display: flex;
  align-items: center;
  gap: 6px;
}

.seat-val {
  font-weight: 600;
  color: #1e293b;
}

/* Card Footer */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid #f1f5f9;
}

.create-time {
  font-size: 11.5px;
  color: #94a3b8;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pay-btn-link {
  text-decoration: none;
}

/* Checklist Modal */
.checklist-modal-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.checklist-dest-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  padding: 10px 14px;
}

.banner-icon {
  font-size: 24px;
}

.banner-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.b-dest {
  font-size: 13px;
  font-weight: 700;
  color: #166534;
}

.b-tip {
  font-size: 11.5px;
  color: #15803d;
}

.checklist-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.check-group {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 14px;
}

.group-title {
  font-size: 12.5px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 6px;
}

.group-items {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: #475569;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
</style>
