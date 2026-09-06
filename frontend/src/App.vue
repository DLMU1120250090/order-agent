<template>
  <div class="app-layout">
    <!-- Topbar Header -->
    <header class="topbar">
      <div class="brand">
        <div class="brand-badge">行</div>
        <div class="brand-text">
          <div class="brand-title">出行规划与预订助手</div>
          <div class="brand-subtitle">规划 · 下单 · 记忆 · 可观测 · 评测闭环</div>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <nav class="nav-links">
        <router-link to="/travel/chat" class="nav-item" active-class="active">
          <el-icon><ChatDotRound /></el-icon>
          <span>助手</span>
        </router-link>
        <router-link to="/travel/orders" class="nav-item" active-class="active">
          <el-icon><List /></el-icon>
          <span>订单</span>
        </router-link>
        <router-link to="/travel/memory" class="nav-item" active-class="active">
          <el-icon><Cpu /></el-icon>
          <span>Memory</span>
        </router-link>
        <router-link to="/admin/traces" class="nav-item" active-class="active">
          <el-icon><TrendCharts /></el-icon>
          <span>Trace</span>
        </router-link>
        <router-link to="/admin/evaluations" class="nav-item" active-class="active">
          <el-icon><DataAnalysis /></el-icon>
          <span>Evaluation</span>
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
      <router-view />
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
  font-weight: 700;
  font-size: 18px;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
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
