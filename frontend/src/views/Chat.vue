<template>
  <div class="workspace-container">
    <!-- Left: Session History Sidebar (ChatGPT style) -->
    <SessionSidebar />

    <!-- Center: Conversation Area -->
    <section class="conversation-pane">
      <!-- Session Bar -->
      <div class="session-bar">
        <div class="session-info">
          <!-- Expand sidebar button when collapsed -->
          <button
            v-if="chatStore.isSidebarCollapsed"
            type="button"
            class="sidebar-expand-btn"
            title="展开会话历史"
            @click="chatStore.toggleSidebar"
          >
            <el-icon><Expand /></el-icon>
          </button>
          <span class="session-dot"></span>
          <span class="session-label">当前会话:</span>
          <span class="session-title-tag" :title="currentSessionTitle">{{ currentSessionTitle }}</span>
          <span class="session-id">({{ chatStore.sessionId || '正在连接...' }})</span>
        </div>
        <div class="session-actions">
          <el-button size="small" plain @click="handleNewSession">
            <el-icon><Plus /></el-icon>
            新会话
          </el-button>
        </div>
      </div>

      <!-- Messages Stream Scrollable Container -->
      <div ref="messagesContainer" class="messages-stream">
        <MessageBubble
          v-for="msg in chatStore.messages"
          :key="msg.id"
          :message="msg"
        />
        <div v-if="chatStore.isSending" class="thinking-bubble">
          <span class="thinking-avatar">🐟</span>
          <div class="thinking-card">
            <span class="thinking-pulse"></span>
            <span class="thinking-text">Agent 正在分析需求并调用规划模型...</span>
          </div>
        </div>
      </div>

      <!-- Quick Question Chips -->
      <div class="quick-questions">
        <button
          v-for="q in QUICK_QUESTIONS"
          :key="q"
          type="button"
          class="quick-chip"
          :disabled="chatStore.isSending"
          @click="sendQuickQuestion(q)"
        >
          {{ q }}
        </button>
      </div>

      <!-- Input Area -->
      <div class="input-pane">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :rows="2"
          placeholder="输入您的出行需求（例如：“帮我规划下周三去成都，经济型”），按 Enter 发送，Shift+Enter 换行"
          :disabled="chatStore.isSending"
          resize="none"
          class="chat-textarea"
          @keydown="handleKeydown"
        />
        <div class="input-bottom-bar">
          <span class="input-hint">Enter 发送 · Shift+Enter 换行</span>
          <el-button
            type="primary"
            class="send-btn"
            :loading="chatStore.isSending"
            :disabled="!inputMessage.trim()"
            @click="handleSend"
          >
            <el-icon><Position /></el-icon>
            发送
          </el-button>
        </div>
      </div>
    </section>

    <!-- Right 30%: Runtime Panel Area -->
    <aside class="runtime-pane">
      <div class="runtime-header">
        <div class="runtime-title">
          <el-icon><Cpu /></el-icon>
          <span>Runtime 运行时面板</span>
        </div>
        <div class="runtime-header-right">
          <span class="runtime-tag" :class="{ active: !!runtimeStore.traceDetail }">
            {{ runtimeStore.traceDetail ? '已点亮 · 实时' : '等待触发' }}
          </span>
        </div>
      </div>

      <!-- Tab Switcher -->
      <div class="runtime-tabs">
        <button
          type="button"
          class="runtime-tab-btn"
          :class="{ active: runtimeStore.activeTab === 'pipeline' }"
          @click="runtimeStore.activeTab = 'pipeline'"
        >
          <el-icon><Operation /></el-icon>
          <span>Agent 流水</span>
        </button>
        <button
          type="button"
          class="runtime-tab-btn"
          :class="{ active: runtimeStore.activeTab === 'memory' }"
          @click="runtimeStore.activeTab = 'memory'"
        >
          <el-icon><Collection /></el-icon>
          <span>生效记忆</span>
          <span v-if="runtimeStore.memoryItems.length > 0" class="tab-badge">
            {{ runtimeStore.memoryItems.length }}
          </span>
        </button>
        <button
          type="button"
          class="runtime-tab-btn"
          :class="{ active: runtimeStore.activeTab === 'trace' }"
          @click="runtimeStore.activeTab = 'trace'"
        >
          <el-icon><DataLine /></el-icon>
          <span>轨迹快照</span>
          <span v-if="runtimeStore.events.length > 0" class="tab-badge">
            {{ runtimeStore.events.length }}
          </span>
        </button>
      </div>

      <!-- Tab Content Area with Loading -->
      <div v-loading="runtimeStore.isLoading" class="runtime-content">
        <AgentStatus v-if="runtimeStore.activeTab === 'pipeline'" />
        <MemoryContext v-else-if="runtimeStore.activeTab === 'memory'" />
        <TracePreview v-else-if="runtimeStore.activeTab === 'trace'" />
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'ChatView' })
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore, QUICK_QUESTIONS } from '@/stores/chat'
import { useRuntimeStore } from '@/stores/runtime'
import { useUserStore } from '@/stores/user'
import SessionSidebar from '@/components/chat/SessionSidebar.vue'
import MessageBubble from '@/components/chat/MessageBubble.vue'
import AgentStatus from '@/components/runtime/AgentStatus.vue'
import MemoryContext from '@/components/runtime/MemoryContext.vue'
import TracePreview from '@/components/runtime/TracePreview.vue'

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const runtimeStore = useRuntimeStore()
const userStore = useUserStore()
const inputMessage = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

const currentSessionTitle = computed(() => {
  const current = chatStore.sessionList.find(s => s.sessionId === chatStore.sessionId)
  return current?.title || '新出行规划会话'
})

async function checkRoutePrompt() {
  const prompt = (route.query.prompt as string)?.trim()
  if (prompt && !chatStore.isSending) {
    // Clean query parameter from URL to prevent accidental resend on page refresh
    router.replace({ path: '/travel/chat' })
    await nextTick()
    if (!chatStore.sessionId) {
      await chatStore.initSession()
    }
    await chatStore.sendMessage(prompt)
    nextTick(() => scrollToBottom())
  }
}

onMounted(async () => {
  await chatStore.initSession()
  scrollToBottom()
  await checkRoutePrompt()
})

watch(
  () => route.query.prompt,
  async (newPrompt) => {
    if (newPrompt) {
      await checkRoutePrompt()
    }
  }
)

// Refetch if user changes
watch(
  () => userStore.userId,
  async () => {
    await chatStore.initSession()
  }
)

watch(
  () => chatStore.messages.length,
  () => {
    nextTick(() => {
      scrollToBottom()
    })
  }
)

watch(
  () => chatStore.latestTraceId,
  (newTraceId) => {
    if (newTraceId) {
      runtimeStore.fetchTrace(newTraceId)
    } else {
      runtimeStore.reset()
    }
  },
  { immediate: true }
)

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

async function handleSend() {
  const text = inputMessage.value.trim()
  if (!text || chatStore.isSending) return
  inputMessage.value = ''
  await chatStore.sendMessage(text)
  nextTick(() => scrollToBottom())
}

function sendQuickQuestion(q: string) {
  inputMessage.value = ''
  chatStore.sendMessage(q)
  nextTick(() => scrollToBottom())
}

async function handleNewSession() {
  runtimeStore.reset()
  await chatStore.createNewSession()
}
</script>

<style scoped>
.workspace-container {
  display: flex;
  height: 100%;
  width: 100%;
  background: #f8fafc;
  overflow: hidden;
}

/* Left 70% Conversation Pane */
.conversation-pane {
  flex: 7;
  display: flex;
  flex-direction: column;
  height: 100%;
  border-right: 1px solid #e2e8f0;
  background: #f8fafc;
  min-width: 0;
}

.session-bar {
  height: 44px;
  background: #ffffff;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  flex-shrink: 0;
}

.session-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.sidebar-expand-btn {
  background: transparent;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 3px 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #475569;
  margin-right: 4px;
  transition: all 0.15s ease;
}

.sidebar-expand-btn:hover {
  background: #eff6ff;
  color: #2563eb;
  border-color: #93c5fd;
}

.session-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
}

.session-label {
  color: #94a3b8;
}

.session-title-tag {
  font-weight: 700;
  color: #0f172a;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-id {
  font-family: monospace;
  color: #94a3b8;
  font-size: 11px;
}

.messages-stream {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  scroll-behavior: smooth;
}

.thinking-bubble {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.thinking-avatar {
  font-size: 18px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #e0f2fe;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thinking-card {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  padding: 10px 16px;
  border-radius: 12px;
  font-size: 13px;
  color: #64748b;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
}

.thinking-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3b82f6;
  animation: pulse-blue 1.5s infinite;
}

@keyframes pulse-blue {
  0% { transform: scale(0.9); opacity: 0.6; }
  50% { transform: scale(1.2); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.6; }
}

.quick-questions {
  display: flex;
  gap: 6px;
  padding: 8px 18px;
  overflow-x: auto;
  white-space: nowrap;
  background: #ffffff;
  border-top: 1px solid #f1f5f9;
  flex-shrink: 0;
}

.quick-chip {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 9999px;
  padding: 4px 12px;
  font-size: 12px;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s ease;
}

.quick-chip:hover:not(:disabled) {
  background: #e0f2fe;
  color: #0284c7;
  border-color: #bae6fd;
}

.input-pane {
  background: #ffffff;
  border-top: 1px solid #e2e8f0;
  padding: 12px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.input-bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.input-hint {
  font-size: 11px;
  color: #94a3b8;
}

.send-btn {
  border-radius: 8px;
  padding: 8px 18px;
}

/* Right 30% Runtime Pane */
.runtime-pane {
  flex: 3;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  height: 100%;
  min-width: 280px;
  max-width: 400px;
}

.runtime-header {
  height: 44px;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  flex-shrink: 0;
}

.runtime-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.runtime-tag {
  font-size: 11px;
  background: #f1f5f9;
  color: #64748b;
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 600;
  transition: all 0.2s ease;
}

.runtime-tag.active {
  background: #eff6ff;
  color: #2563eb;
}

.runtime-tabs {
  display: flex;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  padding: 4px 8px 0;
  gap: 4px;
  flex-shrink: 0;
}

.runtime-tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 6px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 12px;
  font-weight: 500;
  color: #64748b;
  cursor: pointer;
  border-radius: 6px 6px 0 0;
  transition: all 0.15s ease;
}

.runtime-tab-btn:hover {
  color: #0f172a;
  background: #f1f5f9;
}

.runtime-tab-btn.active {
  color: #2563eb;
  font-weight: 600;
  border-bottom-color: #2563eb;
  background: #ffffff;
}

.tab-badge {
  font-size: 10px;
  background: #e0f2fe;
  color: #0284c7;
  padding: 0 5px;
  border-radius: 9999px;
  font-weight: 700;
}

.runtime-content {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
</style>
