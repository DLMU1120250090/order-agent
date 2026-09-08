<template>
  <div class="memory-workspace">
    <!-- Topbar -->
    <header class="memory-topbar">
      <div class="topbar-left">
        <div class="page-title">
          <el-icon><Collection /></el-icon>
          <span>Memory Center 记忆中心全生命周期</span>
        </div>

        <!-- Tab Switcher -->
        <div class="memory-nav-tabs">
          <button
            type="button"
            class="nav-tab"
            :class="{ active: activeTab === 'profile' }"
            @click="activeTab = 'profile'"
          >
            <el-icon><User /></el-icon>
            <span>L1 偏好画像</span>
          </button>
          <button
            type="button"
            class="nav-tab"
            :class="{ active: activeTab === 'episodes' }"
            @click="activeTab = 'episodes'"
          >
            <el-icon><Tickets /></el-icon>
            <span>L2 历史经历库</span>
            <span class="tab-badge">{{ memoryStore.episodes.length }}</span>
          </button>
          <button
            type="button"
            class="nav-tab"
            :class="{ active: activeTab === 'distill' }"
            @click="activeTab = 'distill'"
          >
            <el-icon><Document /></el-icon>
            <span>L3 长期蒸馏报告</span>
          </button>
        </div>
      </div>

      <div class="topbar-right">
        <el-button
          size="small"
          plain
          :loading="memoryStore.isLoading"
          @click="memoryStore.fetchAll"
        >
          <el-icon><Refresh /></el-icon>
          刷新记忆库
        </el-button>
      </div>
    </header>

    <!-- Main Content Area with Loading -->
    <main v-loading="memoryStore.isLoading" class="memory-main-pane">
      <!-- Tab 1: L1 Profile -->
      <section v-if="activeTab === 'profile'" class="tab-content">
        <MemoryCard :profile="memoryStore.profile" />
      </section>

      <!-- Tab 2: L2 Memory -->
      <section v-else-if="activeTab === 'episodes'" class="tab-content">
        <!-- Sub-switcher for Passenger L2 vs User L2 -->
        <div class="l2-sub-nav">
          <div class="sub-nav-left">
            <button
              type="button"
              class="sub-tab"
              :class="{ active: l2Scope === 'passenger' }"
              @click="l2Scope = 'passenger'"
            >
              <span>🚄 乘车人出行经历 (Passenger L2)</span>
              <span class="sub-badge">{{ memoryStore.episodes.length }}</span>
            </button>
            <button
              type="button"
              class="sub-tab"
              :class="{ active: l2Scope === 'user' }"
              @click="l2Scope = 'user'"
            >
              <span>👤 操作者决策行为流 (User L2)</span>
              <span class="sub-badge user">{{ memoryStore.userEvents.length }}</span>
            </button>
          </div>
          <div class="sub-nav-tip">
            <span v-if="l2Scope === 'passenger'">记录乘车人真实出行、车次座席与履约评价</span>
            <span v-else>记录使用者决策行为：降价响应、推荐采纳与改签退票</span>
          </div>
        </div>

        <!-- Passenger Episodes View -->
        <div v-if="l2Scope === 'passenger'">
          <div v-if="memoryStore.episodes.length === 0" class="empty-box">
            <el-empty description="暂无历史行程经历 (Passenger L2 Episodes)" />
          </div>
          <div v-else class="episodes-list">
            <EpisodeCard
              v-for="ep in memoryStore.episodes"
              :key="ep.id"
              :episode="ep"
            />
          </div>
        </div>

        <!-- User Events View -->
        <div v-else-if="l2Scope === 'user'">
          <div v-if="memoryStore.userEvents.length === 0" class="empty-box">
            <el-empty description="暂无操作者行为事件 (User L2 Events)" />
          </div>
          <div v-else class="events-list">
            <UserEventCard
              v-for="ev in memoryStore.userEvents"
              :key="ev.id"
              :event="ev"
            />
          </div>
        </div>
      </section>

      <!-- Tab 3: L3 Distill Report -->
      <section v-else-if="activeTab === 'distill'" class="tab-content">
        <DistillViewer />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useMemoryStore } from '@/stores/memory'
import { useUserStore } from '@/stores/user'
import MemoryCard from '@/components/memory/MemoryCard.vue'
import EpisodeCard from '@/components/memory/EpisodeCard.vue'
import UserEventCard from '@/components/memory/UserEventCard.vue'
import DistillViewer from '@/components/memory/DistillViewer.vue'

const memoryStore = useMemoryStore()
const userStore = useUserStore()
const activeTab = ref<'profile' | 'episodes' | 'distill'>('profile')
const l2Scope = ref<'passenger' | 'user'>('passenger')

onMounted(async () => {
  await memoryStore.fetchAll()
})

// Refetch if user changes
watch(
  () => userStore.userId,
  async () => {
    await memoryStore.fetchAll()
  }
)
</script>

<style scoped>
.memory-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: #f8fafc;
  overflow: hidden;
}

.memory-topbar {
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

.memory-nav-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #f1f5f9;
  padding: 3px;
  border-radius: 8px;
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: none;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 500;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s ease;
}

.nav-tab:hover {
  color: #0f172a;
}

.nav-tab.active {
  background: #ffffff;
  color: #2563eb;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.tab-badge {
  font-size: 10.5px;
  background: #e0f2fe;
  color: #0284c7;
  padding: 1px 6px;
  border-radius: 9999px;
  font-weight: 700;
}

.memory-main-pane {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

.tab-content {
  max-width: 1000px;
  margin: 0 auto;
}

.episodes-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.l2-sub-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 8px 14px;
  margin-bottom: 14px;
}

.sub-nav-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sub-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s ease;
}

.sub-tab:hover {
  color: #1e293b;
  border-color: #cbd5e1;
}

.sub-tab.active {
  background: #eff6ff;
  color: #2563eb;
  border-color: #93c5fd;
}

.sub-badge {
  font-size: 11px;
  background: #e2e8f0;
  color: #475569;
  padding: 1px 6px;
  border-radius: 9999px;
  font-weight: 700;
}

.sub-tab.active .sub-badge {
  background: #dbeafe;
  color: #1d4ed8;
}

.sub-badge.user {
  background: #f3e8ff;
  color: #7e22ce;
}

.sub-tab.active .sub-badge.user {
  background: #f3e8ff;
  color: #7e22ce;
}

.sub-nav-tip {
  font-size: 12px;
  color: #94a3b8;
}

.empty-box {
  background: #ffffff;
  border-radius: 12px;
  padding: 60px 0;
  border: 1px solid #e2e8f0;
}
</style>
