<template>
  <aside
    class="session-sidebar"
    :class="{ collapsed: chatStore.isSidebarCollapsed }"
  >
    <!-- Top Header -->
    <div class="sidebar-top">
      <div class="brand-row">
        <div class="brand-left">
          <span class="brand-icon">💬</span>
          <span class="brand-title">对话历史</span>
        </div>
        <div class="brand-actions">
          <button
            type="button"
            class="icon-btn"
            title="折叠侧边栏"
            @click="chatStore.toggleSidebar"
          >
            <el-icon><Fold /></el-icon>
          </button>
        </div>
      </div>

      <!-- New Chat Button -->
      <button
        type="button"
        class="new-chat-btn"
        :disabled="chatStore.isSending"
        @click="handleNewChat"
      >
        <el-icon><Plus /></el-icon>
        <span>新建对话</span>
      </button>

      <!-- Search Input -->
      <div class="search-box">
        <el-input
          v-model="searchQuery"
          placeholder="搜索历史会话..."
          size="small"
          clearable
          class="sidebar-search"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>
    </div>

    <!-- Recent Sessions List -->
    <div v-loading="chatStore.isLoadingSessions" class="sessions-scroll">
      <div class="group-title">最近 (Recent)</div>

      <div v-if="filteredSessions.length === 0" class="empty-sessions">
        <span v-if="searchQuery">未搜到匹配的会话</span>
        <span v-else>暂无历史会话记录</span>
      </div>

      <div class="sessions-list">
        <div
          v-for="s in filteredSessions"
          :key="s.sessionId"
          class="session-item"
          :class="{ active: s.sessionId === chatStore.sessionId }"
          @click="chatStore.switchSession(s.sessionId)"
        >
          <div class="session-item-content">
            <span class="item-icon">💬</span>
            <span class="item-title" :title="s.title">{{ s.title }}</span>
          </div>

          <!-- Hover Action Menu -->
          <div class="item-actions" @click.stop>
            <el-dropdown trigger="click" @command="(cmd: string) => handleMenuCommand(cmd, s)">
              <button type="button" class="more-btn" title="更多操作">
                <el-icon><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">
                    <el-icon><EditPen /></el-icon>
                    <span>重命名</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided class="danger-item">
                    <el-icon><Delete /></el-icon>
                    <span>删除对话</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom User Section -->
    <div class="sidebar-footer">
      <div class="user-pill">
        <div class="user-avatar">👤</div>
        <div class="user-info-text">
          <span class="user-name">User {{ userStore.userId }}</span>
          <span class="user-desc">已连接本地服务</span>
        </div>
      </div>
    </div>

    <!-- Rename Dialog -->
    <el-dialog
      v-model="renameDialogVisible"
      title="修改会话标题"
      width="400px"
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item label="会话标题">
          <el-input
            v-model="newTitleInput"
            placeholder="请输入会话标题"
            maxlength="40"
            show-word-limit
            @keydown.enter.prevent="submitRename"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!newTitleInput.trim()" @click="submitRename">
          确定修改
        </el-button>
      </template>
    </el-dialog>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'
import type { SessionItem } from '@/types/chat'

const chatStore = useChatStore()
const userStore = useUserStore()

const searchQuery = ref('')
const renameDialogVisible = ref(false)
const targetSession = ref<SessionItem | null>(null)
const newTitleInput = ref('')

const filteredSessions = computed(() => {
  if (!searchQuery.value.trim()) {
    return chatStore.sessionList
  }
  const q = searchQuery.value.trim().toLowerCase()
  return chatStore.sessionList.filter(s => (s.title || '').toLowerCase().includes(q))
})

async function handleNewChat() {
  await chatStore.createNewSession()
}

function handleMenuCommand(cmd: string, s: SessionItem) {
  if (cmd === 'rename') {
    targetSession.value = s
    newTitleInput.value = s.title
    renameDialogVisible.value = true
  } else if (cmd === 'delete') {
    ElMessageBox.confirm(`确定要删除会话「${s.title}」吗？删除后不可恢复喵。`, '删除确认', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    }).then(async () => {
      await chatStore.deleteSession(s.sessionId)
    }).catch(() => {})
  }
}

async function submitRename() {
  if (!targetSession.value || !newTitleInput.value.trim()) return
  await chatStore.renameSession(targetSession.value.sessionId, newTitleInput.value.trim())
  renameDialogVisible.value = false
}
</script>

<style scoped>
.session-sidebar {
  width: 250px;
  height: 100%;
  background: #f8fafc;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.25s ease, transform 0.25s ease;
  overflow: hidden;
  user-select: none;
}

.session-sidebar.collapsed {
  width: 0;
  border-right: none;
  visibility: hidden;
}

.sidebar-top {
  padding: 12px 14px 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
  border-bottom: 1px solid #f1f5f9;
}

.brand-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.brand-icon {
  font-size: 16px;
}

.brand-title {
  font-size: 13.5px;
  font-weight: 700;
  color: #0f172a;
}

.brand-actions {
  display: flex;
  align-items: center;
}

.icon-btn {
  background: transparent;
  border: none;
  font-size: 16px;
  color: #64748b;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.icon-btn:hover {
  background: #e2e8f0;
  color: #0f172a;
}

.new-chat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  color: #1e293b;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
  transition: all 0.15s ease;
}

.new-chat-btn:hover:not(:disabled) {
  background: #eff6ff;
  border-color: #93c5fd;
  color: #2563eb;
}

.search-box {
  width: 100%;
}

.sidebar-search :deep(.el-input__wrapper) {
  background: #ffffff;
  border-radius: 6px;
}

.sessions-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 10px 10px 14px;
  display: flex;
  flex-direction: column;
}

.group-title {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  padding: 4px 8px 6px;
  text-transform: uppercase;
}

.empty-sessions {
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
  padding: 30px 0;
}

.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
}

.session-item:hover {
  background: #e2e8f0;
}

.session-item.active {
  background: #e0f2fe;
  color: #0369a1;
  font-weight: 600;
}

.session-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 3px;
  background: #2563eb;
  border-radius: 0 2px 2px 0;
}

.session-item-content {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  flex: 1;
}

.item-icon {
  font-size: 13px;
  opacity: 0.7;
}

.item-title {
  font-size: 12.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  color: #334155;
}

.session-item.active .item-title {
  color: #0369a1;
}

.item-actions {
  display: flex;
  align-items: center;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.session-item:hover .item-actions,
.session-item.active .item-actions {
  opacity: 1;
}

.more-btn {
  background: transparent;
  border: none;
  font-size: 13px;
  color: #64748b;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.more-btn:hover {
  background: #cbd5e1;
  color: #0f172a;
}

.sidebar-footer {
  padding: 10px 14px;
  border-top: 1px solid #f1f5f9;
  background: #ffffff;
  flex-shrink: 0;
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #eff6ff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  border: 1px solid #bfdbfe;
}

.user-info-text {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.user-desc {
  font-size: 10.5px;
  color: #94a3b8;
}

.danger-item {
  color: #dc2626;
}
</style>
