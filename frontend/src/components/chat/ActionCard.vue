<template>
  <div class="action-card">
    <!-- Header -->
    <div class="action-header">
      <div class="action-badge">
        <el-icon><Ticket /></el-icon>
        <span>订单履约状态机</span>
      </div>
      <span v-if="orderNo" class="order-no">订单号: {{ orderNo }}</span>
    </div>

    <!-- Step Progress Bar -->
    <div class="steps-progress">
      <div class="step-node" :class="{ completed: step >= 1, active: step === 1 }">
        <div class="node-circle">1</div>
        <span class="node-text">创建订单</span>
      </div>
      <div class="step-connector" :class="{ active: step >= 2 }"></div>
      <div class="step-node" :class="{ completed: step >= 2, active: step === 2 }">
        <div class="node-circle">2</div>
        <span class="node-text">锁定座位</span>
      </div>
      <div class="step-connector" :class="{ active: step >= 3 }"></div>
      <div class="step-node" :class="{ completed: step >= 3, active: step === 3 }">
        <div class="node-circle">3</div>
        <span class="node-text">待支付</span>
      </div>
    </div>

    <!-- Status Message -->
    <div class="status-box">
      <div class="status-indicator">
        <span class="pulse-dot"></span>
        <span class="status-title">{{ statusTitle }}</span>
      </div>
      <p class="status-desc">{{ statusDesc }}</p>
    </div>

    <!-- QR Code / Checkout Preview -->
    <div v-if="hasQrCode || step >= 2" class="checkout-preview">
      <div class="qr-wrapper">
        <img
          :src="qrImageUrl"
          alt="支付二维码"
          class="qr-img"
          @error="onQrError"
        />
        <div class="qr-tip">
          <span class="qr-tip-main">微信/支付宝 扫码支付</span>
          <span class="qr-tip-sub">支持本人支付 · Agent 绝不代付</span>
        </div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="action-buttons">
      <el-button
        type="primary"
        size="small"
        class="checkout-btn"
        @click="openCheckout"
      >
        <el-icon><CreditCard /></el-icon>
        前往 Mock 收银台支付
      </el-button>
      <el-button
        size="small"
        @click="confirmPaid"
      >
        我已完成支付
      </el-button>
      <router-link to="/travel/orders" class="view-order-link">
        查看我的订单 ➔
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  orderNo?: string
  taskId?: string
  blocks?: any[]
  text?: string
}>()

const chatStore = useChatStore()
const qrFallback = ref(false)

const step = computed(() => {
  const t = props.text || ''
  if (t.includes('付好了') || t.includes('已出票') || t.includes('支付成功')) {
    return 3
  }
  if (t.includes('锁定座位') || t.includes('已锁定') || t.includes('待支付') || props.orderNo) {
    return 2
  }
  return 1
})

const statusTitle = computed(() => {
  if (step.value === 3) return '订单已进入支付核销'
  if (step.value === 2) return '座位锁定成功 · 等待支付'
  return '订单正在异步处理中...'
})

const statusDesc = computed(() => {
  if (step.value >= 2) {
    return '请于 15 分钟内完成支付。订单将由 12306 模拟平台自动出票。'
  }
  return 'Agent 正在为您连接铁路/航空数据接口提交购票请求。'
})

const hasQrCode = computed(() => {
  return props.blocks?.some((b) => b.type === 'IMAGE' || b.imagePath) || true
})

const qrImageUrl = computed(() => {
  if (qrFallback.value) {
    // Generates deterministically derived SVG placeholder if file not present
    return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect fill="%23f8fafc" width="100" height="100"/><rect fill="%232563eb" x="10" y="10" width="30" height="30"/><rect fill="%232563eb" x="60" y="10" width="30" height="30"/><rect fill="%232563eb" x="10" y="60" width="30" height="30"/><rect fill="%230f172a" x="50" y="50" width="10" height="10"/><text x="50" y="85" font-size="10" text-anchor="middle" fill="%2364748b">MOCK PAY</text></svg>`
  }
  return '/media/qr_code.jpg'
})

function onQrError() {
  qrFallback.value = true
}

function openCheckout() {
  const order = props.orderNo || 'ORD-DEMO'
  const url = `/mock/checkout.html?order_no=${encodeURIComponent(order)}&price=553&auto_pay=2`
  window.open(url, '_blank', 'width=560,height=640')
}

function confirmPaid() {
  chatStore.sendMessage('付好了')
}
</script>

<style scoped>
.action-card {
  margin-top: 10px;
  background: #ffffff;
  border: 1px solid #dbeafe;
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.06);
}

.action-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.action-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1d4ed8;
}

.order-no {
  font-family: monospace;
  font-size: 11px;
  color: #64748b;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
}

.steps-progress {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding: 0 10px;
}

.step-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.node-circle {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #e2e8f0;
  color: #64748b;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  transition: all 0.2s ease;
}

.step-node.completed .node-circle {
  background: #2563eb;
  color: #ffffff;
}

.step-node.active .node-circle {
  background: #3b82f6;
  color: #ffffff;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}

.node-text {
  font-size: 11px;
  color: #64748b;
}

.step-node.active .node-text,
.step-node.completed .node-text {
  color: #0f172a;
  font-weight: 600;
}

.step-connector {
  flex: 1;
  height: 2px;
  background: #e2e8f0;
  margin: 0 8px;
  margin-bottom: 16px;
  transition: all 0.2s ease;
}

.step-connector.active {
  background: #2563eb;
}

.status-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.3);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); opacity: 0.8; }
  50% { transform: scale(1.15); opacity: 1; }
  100% { transform: scale(0.95); opacity: 0.8; }
}

.status-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.status-desc {
  font-size: 11.5px;
  color: #64748b;
  line-height: 1.5;
}

.checkout-preview {
  margin-bottom: 14px;
}

.qr-wrapper {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #eff6ff;
  border: 1px dashed #bfdbfe;
  border-radius: 8px;
  padding: 10px 12px;
}

.qr-img {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  background: #ffffff;
  border: 1px solid #dbeafe;
}

.qr-tip {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.qr-tip-main {
  font-size: 13px;
  font-weight: 600;
  color: #1e3a8a;
}

.qr-tip-sub {
  font-size: 11px;
  color: #60a5fa;
}

.action-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.checkout-btn {
  border-radius: 6px;
}

.view-order-link {
  margin-left: auto;
  font-size: 12px;
  color: #2563eb;
  text-decoration: none;
}

.view-order-link:hover {
  text-decoration: underline;
}
</style>
