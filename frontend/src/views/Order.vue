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
                <div class="step-circle">4</div>
                <span class="step-label">已出行</span>
              </div>
            </div>

            <!-- Route & Legs Content -->
            <div class="card-body-content">
              <div class="route-banner">
                <div class="transport-badge">
                  {{ isFlight(order) ? '✈️ 航班' : '🚄 高铁' }}
                </div>
                <div class="route-cities">
                  <span class="city-name">{{ getOrigin(order) }}</span>
                  <div class="route-line-box">
                    <span class="v-num">{{ getVehicleNo(order) }}</span>
                    <div class="route-arrow-line"></div>
                  </div>
                  <span class="city-name">{{ getDestination(order) }}</span>
                </div>
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
                      {{ typeof p === 'string' ? p : p.name || p.passenger_id || `出行人 ${pIdx + 1}` }}
                    </span>
                  </div>
                </div>

                <div class="seat-info-box">
                  <span class="lbl">席位:</span>
                  <span class="seat-val">{{ getSeatType(order) }}</span>
                </div>
              </div>
            </div>

            <!-- Card Bottom Action Bar -->
            <div class="card-footer">
              <div class="footer-left">
                <span class="create-time">创建时间: {{ formatDate(order.createdAt) }}</span>
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

                <!-- Change Ticket Button -->
                <el-button
                  v-if="order.status === 'PAID'"
                  size="small"
                  plain
                  @click="goToChatWithAction(`我想改签订单 ${getOrderNo(order)}`)"
                >
                  <el-icon><Switch /></el-icon>
                  申请改签
                </el-button>

                <!-- Refund Button -->
                <el-button
                  v-if="order.status === 'PAID'"
                  size="small"
                  plain
                  type="danger"
                  @click="goToChatWithAction(`帮我退掉订单 ${getOrderNo(order)}`)"
                >
                  <el-icon><CloseBold /></el-icon>
                  申请退票
                </el-button>

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
import { ElMessage } from 'element-plus'
import { useOrderStore } from '@/stores/order'
import type { TravelOrder } from '@/types/order'

const router = useRouter()
const orderStore = useOrderStore()

const STATUS_TABS = [
  { key: 'ALL', label: '全部订单' },
  { key: 'LOCKED', label: '待支付 (已锁座)' },
  { key: 'PAID', label: '已支付 (待出行)' },
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
  const type = order.type || (order.legs && order.legs[0]?.type) || ''
  return String(type).toUpperCase().includes('FLIGHT')
}

function getOrigin(order: any): string {
  if (order.legs && order.legs.length > 0) {
    return order.legs[0].origin || '出发地'
  }
  return '上海'
}

function getDestination(order: any): string {
  if (order.legs && order.legs.length > 0) {
    return order.legs[order.legs.length - 1].destination || '目的地'
  }
  return '成都'
}

function getVehicleNo(order: any): string {
  if (order.legs && order.legs.length > 0) {
    return order.legs[0].vehicle_no || order.legs[0].train_no || 'G1234'
  }
  return 'G1234 次'
}

function getSeatType(order: any): string {
  if (order.legs && order.legs.length > 0) {
    return order.legs[0].seat_type || order.legs[0].seat || '二等座'
  }
  return '二等座'
}

function getPassengers(order: any): any[] {
  if (Array.isArray(order.passengers) && order.passengers.length > 0) {
    return order.passengers
  }
  return ['本人 (已实名)']
}

function statusText(status?: string): string {
  switch ((status || '').toUpperCase()) {
    case 'CREATED': return '已创建'
    case 'LOCKED': return '已锁座 · 待支付'
    case 'PAID': return '已支付 · 待出行'
    case 'CHANGED': return '已改签'
    case 'REFUNDED': return '已全额退票'
    case 'CANCELLED': return '已取消'
    default: return status || '进行中'
  }
}

function statusClass(status?: string): string {
  switch ((status || '').toUpperCase()) {
    case 'LOCKED': return 'status-locked'
    case 'PAID': return 'status-paid'
    case 'CHANGED': return 'status-changed'
    case 'REFUNDED': return 'status-refunded'
    default: return 'status-default'
  }
}

function stepClass(status: string | undefined, stepNo: number): string {
  const s = (status || '').toUpperCase()
  let currentStep = 1
  if (s === 'LOCKED') currentStep = 2
  else if (s === 'PAID' || s === 'CHANGED') currentStep = 3
  else if (s === 'COMPLETED') currentStep = 4

  if (stepNo < currentStep) return 'finished'
  if (stepNo === currentStep) return 'active'
  return 'pending'
}

function stepFilled(status: string | undefined, stepNo: number): boolean {
  const s = (status || '').toUpperCase()
  let currentStep = 1
  if (s === 'LOCKED') currentStep = 2
  else if (s === 'PAID' || s === 'CHANGED') currentStep = 3
  else if (s === 'COMPLETED') currentStep = 4
  return stepNo <= currentStep
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
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
.status-changed { background: #fef3c7; color: #b45309; }
.status-refunded { background: #fee2e2; color: #b91c1c; }
.status-default { background: #f1f5f9; color: #64748b; }

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
  padding: 10px 14px;
  background: #f8fafc;
  border-radius: 8px;
}

.transport-badge {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}

.route-cities {
  display: flex;
  align-items: center;
  gap: 14px;
}

.city-name {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.route-line-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 80px;
}

.v-num {
  font-family: monospace;
  font-size: 10.5px;
  color: #64748b;
}

.route-arrow-line {
  width: 100%;
  height: 2px;
  background: #cbd5e1;
  position: relative;
  margin-top: 2px;
}

.route-arrow-line::after {
  content: '';
  position: absolute;
  right: 0;
  top: -3px;
  border-left: 5px solid #cbd5e1;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
}

.price-box {
  display: flex;
  align-items: baseline;
  color: #ea580c;
}

.currency {
  font-size: 13px;
  font-weight: 700;
}

.amount {
  font-size: 20px;
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
