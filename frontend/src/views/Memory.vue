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

      <!-- Tab 2: L2 Episodes -->
      <section v-else-if="activeTab === 'episodes'" class="tab-content">
        <div v-if="memoryStore.episodes.length === 0" class="empty-box">
          <el-empty description="暂无历史行程经历 (L2 Episodes)" />
        </div>
        <div v-else class="episodes-list">
          <EpisodeCard
            v-for="ep in memoryStore.episodes"
            :key="ep.id"
            :episode="ep"
          />
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
import DistillViewer from '@/components/memory/DistillViewer.vue'

const memoryStore = useMemoryStore()
const userStore = useUserStore()
const activeTab = ref<'profile' | 'episodes' | 'distill'>('profile')

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

.empty-box {
  background: #ffffff;
  border-radius: 12px;
  padding: 60px 0;
  border: 1px solid #e2e8f0;
}
</style>
