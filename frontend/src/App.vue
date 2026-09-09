<template>
  <div class="app-layout">
    <!-- Topbar Header -->
    <header class="topbar">
      <div class="brand">
        <div class="brand-badge" title="出行规划与预订助手">
          <svg class="brand-icon" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M20.665 3.717l-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l-.313 4.694c.46 0 .664-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.785l3.019-14.228c.309-1.239-.473-1.8-1.282-1.435z" />
          </svg>
        </div>
        <div class="brand-text">
          <div class="brand-title">出行规划与预订助手</div>
          <div class="brand-subtitle">规划 · 下单 · 记忆 · 可观测 · 评测闭环</div>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <nav class="nav-links">
        <router-link to="/travel/chat" class="nav-item" active-class="active">
          <el-icon><ChatDotRound /></el-icon>
          <span>规划助手</span>
        </router-link>
        <router-link to="/travel/orders" class="nav-item" active-class="active">
          <el-icon><List /></el-icon>
          <span>订单记录</span>
        </router-link>
        <router-link to="/travel/memory" class="nav-item" active-class="active">
          <el-icon><Cpu /></el-icon>
          <span>记忆中心</span>
        </router-link>
        <router-link to="/admin/traces" class="nav-item" active-class="active">
          <el-icon><TrendCharts /></el-icon>
          <span>链路追踪</span>
        </router-link>
        <router-link to="/admin/evaluations" class="nav-item" active-class="active">
          <el-icon><DataAnalysis /></el-icon>
          <span>质量评测</span>
        </router-link>
      </nav>

      <!-- User ID Switcher -->
      <div class="user-switcher">
        <span class="user-label">调试用户 ID</span>
        <el-input-number
          v-model="currentUserId"
          :min="1"
          :max="999"
          size="small"
          controls-position="right"
          @change="onUserIdChange"
        />
      </div>
    </header>

    <!-- Main View Viewport -->
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <keep-alive include="ChatView,Chat">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { sseService } from '@/services/sse'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const currentUserId = ref(userStore.userId)

watch(
  () => userStore.userId,
  (newVal) => {
    currentUserId.value = newVal
  }
)

function onUserIdChange(val: number | undefined) {
  if (val && val >= 1) {
    userStore.setUserId(val)
    sseService.connect(true)
    ElMessage.success({
      message: `已切换调试用户为 User ${val}`,
      duration: 1500,
    })
  }
}
</script>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: #f8fafc;
}

.topbar {
  height: 60px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  z-index: 50;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-badge {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.brand-icon {
  display: block;
  transform: translate(-1px, 1px);
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.brand-subtitle {
  font-size: 11px;
  color: #64748b;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 13.5px;
  font-weight: 500;
  color: #64748b;
  text-decoration: none;
  transition: all 0.2s ease;
}

.nav-item:hover {
  background-color: #f1f5f9;
  color: #0f172a;
}

.nav-item.active {
  background-color: #eff6ff;
  color: #2563eb;
  font-weight: 600;
}

.user-switcher {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-label {
  font-size: 12px;
  color: #64748b;
}

.main-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}
</style>
