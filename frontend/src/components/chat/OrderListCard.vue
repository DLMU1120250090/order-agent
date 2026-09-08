<template>
  <div class="order-list-card">
    <div class="order-list-header">
      <div class="header-badge">
        <el-icon><Tickets /></el-icon>
        <span>已为您查询到 {{ validOrders.length }} 笔订单</span>
      </div>
      <router-link to="/travel/orders" class="header-link">
        前往订单中心 ➔
      </router-link>
    </div>

    <div class="order-items">
      <div
        v-for="order in validOrders"
        :key="order.orderNo"
        class="order-item"
      >
        <div class="order-item-top">
          <div class="order-meta">
            <span class="order-no">{{ order.orderNo }}</span>
            <span v-if="order.tripDate" class="trip-date">{{ order.tripDate }} 出发</span>
          </div>
          <div class="order-right-meta">
            <el-tag :type="getStatusTagType(order.status)" size="small" effect="light" class="status-tag">
              {{ getStatusLabel(order.status) }}
            </el-tag>
            <span class="order-price">
              <span class="symbol">¥</span>
              <span class="num">{{ order.price }}</span>
            </span>
          </div>
        </div>

        <!-- Legs list inside order -->
        <div v-if="order.legs && order.legs.length > 0" class="order-legs">
          <div v-for="(leg, lIdx) in order.legs" :key="lIdx" class="order-leg-row">
            <div class="leg-mode-badge">
              <el-tag
                size="small"
                :type="leg.mode === 'FLIGHT' ? 'warning' : 'primary'"
                effect="plain"
                class="vehicle-pill"
              >
                {{ leg.mode === 'FLIGHT' ? '✈' : '🚄' }} {{ leg.vehicle_no || leg.mode }}
              </el-tag>
              <el-tag v-if="leg.seat" size="small" type="info" effect="light" class="seat-pill">
                {{ leg.seat }}
              </el-tag>
            </div>
            <div class="leg-route-text">
              <span class="station-depart">{{ leg.from_station || leg.from_city }}</span>
              <span class="time-depart">{{ leg.depart }}</span>
              <span class="arrow-sym">➔</span>
              <span class="station-arrive">{{ leg.to_station || leg.to_city }}</span>
              <span class="time-arrive">{{ leg.arrive }}</span>
            </div>
          </div>
        </div>

        <!-- Passengers inside order -->
        <div v-if="order.passengers && order.passengers.length > 0" class="order-passengers-row">
          <span class="p-label">乘车人:</span>
          <span class="p-names">
            {{ order.passengers.map((p: any) => typeof p === 'string' ? p : (p.name || '乘客')).join('、') }}
            ({{ order.passengers.length }}人)
          </span>
        </div>
      </div>
    </div>

    <div class="order-list-footer">
      <span class="tip-text">需要办理改签、退票或打印出行清单？</span>
      <router-link to="/travel/orders">
        <el-button type="primary" size="small" plain>
          进入订单履约中心管理
        </el-button>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Tickets } from '@element-plus/icons-vue'
import type { OrderBlockItem } from '@/types/chat'

const props = defineProps<{
  orders: any[]
}>()

const validOrders = computed<OrderBlockItem[]>(() => {
  if (!Array.isArray(props.orders)) return []
  return props.orders.filter((b) => b && b.orderNo)
})

function getStatusTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case 'PAID':
    case 'CONFIRMED':
      return 'success'
    case 'BOOKING':
    case 'PENDING_PAY':
      return 'warning'
    case 'CHANGED':
      return ''
    case 'REFUNDED':
    case 'CANCELLED':
      return 'info'
    default:
      return 'info'
  }
}

function getStatusLabel(status: string): string {
  switch (status) {
    case 'PAID':
      return '已出票 (PAID)'
    case 'CONFIRMED':
      return '已确认'
    case 'BOOKING':
      return '出票中'
    case 'PENDING_PAY':
      return '待支付'
    case 'CHANGED':
      return '已改签'
    case 'REFUNDED':
      return '已退票'
    case 'CANCELLED':
      return '已取消'
    default:
      return status || '处理中'
  }
}
</script>

<style scoped>
.order-list-card {
  margin-top: 12px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 3px 12px rgba(15, 23, 42, 0.04);
}

.order-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #e2e8f0;
}

.header-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
}

.header-badge .el-icon {
  color: #2563eb;
  font-size: 16px;
}

.header-link {
  font-size: 12px;
  color: #2563eb;
  text-decoration: none;
  font-weight: 500;
}

.header-link:hover {
  text-decoration: underline;
}

.order-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}

.order-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  transition: all 0.2s ease;
}

.order-item:hover {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

.order-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.order-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.order-no {
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}

.trip-date {
  font-size: 11px;
  color: #64748b;
  background: #e2e8f0;
  padding: 1px 6px;
  border-radius: 4px;
}

.order-right-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-tag {
  font-size: 11px;
  font-weight: 600;
}

.order-price {
  font-weight: 700;
  color: #ef4444;
  font-size: 14px;
}

.order-price .symbol {
  font-size: 11px;
  margin-right: 2px;
}

.order-legs {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dotted #cbd5e1;
}

.order-leg-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}

.leg-mode-badge {
  display: flex;
  align-items: center;
  gap: 4px;
}

.vehicle-pill {
  font-weight: 600;
}

.seat-pill {
  font-size: 10px;
}

.leg-route-text {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #475569;
}

.station-depart,
.station-arrive {
  font-weight: 500;
  color: #1e293b;
}

.time-depart,
.time-arrive {
  font-family: monospace;
  color: #2563eb;
  font-weight: 600;
}

.arrow-sym {
  color: #94a3b8;
  font-size: 10px;
}

.order-passengers-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #f1f5f9;
  font-size: 11px;
}

.p-label {
  color: #64748b;
  font-weight: 500;
}

.p-names {
  color: #0f172a;
  font-weight: 500;
}

.order-list-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #f1f5f9;
}

.tip-text {
  font-size: 12px;
  color: #64748b;
}
</style>
