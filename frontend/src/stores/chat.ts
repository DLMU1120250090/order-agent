import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi } from '@/api/chat'
import { sessionApi } from '@/api/session'
import { sseService } from '@/services/sse'
import type { ChatMessage, SessionItem } from '@/types/chat'
import { ElMessage } from 'element-plus'

export const QUICK_QUESTIONS = [
  '帮我规划下周三去成都，经济型',
  '换一批',
  '就订第一个',
  '付好了',
  '查订单',
  '帮我改到周五',
  '确认改签',
  '把这张票退了吧',
  '给我列个出行清单',
]

const WELCOME_TEXT =
  '你好！我是出行规划与预订助手。告诉我目的地和日期，我可以帮你规划多模式交通、预订下单、智能改签、退票或监控降价。试试点击下方的快捷指令，或输入：帮我规划下周三去成都'

export const useChatStore = defineStore('chat', () => {
  const sessionId = ref<string>('')
  const sessionList = ref<SessionItem[]>([])
  const isLoadingSessions = ref<boolean>(false)
  const isSidebarCollapsed = ref<boolean>(localStorage.getItem('chat.sidebarCollapsed') === 'true')
  const messages = ref<ChatMessage[]>([])
  const isSending = ref<boolean>(false)
  const activeTaskId = ref<string | null>(null)
  const latestTraceId = ref<string | null>(null)

  function toggleSidebar() {
    isSidebarCollapsed.value = !isSidebarCollapsed.value
    localStorage.setItem('chat.sidebarCollapsed', String(isSidebarCollapsed.value))
  }

  // Load user sessions
  async function loadSessionList() {
    isLoadingSessions.value = true
    try {
      const list = await sessionApi.listSessions(50)
      sessionList.value = list || []
    } catch (err) {
      console.warn('[ChatStore] Failed to load sessions:', err)
      sessionList.value = []
    } finally {
      isLoadingSessions.value = false
    }
  }

  // Switch to a specific session
  async function switchSession(targetSessionId: string) {
    if (!targetSessionId) return
    const isSameSession = sessionId.value === targetSessionId && messages.value.length > 0
    sessionId.value = targetSessionId
    if (!isSameSession) {
      messages.value = []
      latestTraceId.value = null
    }

    try {
      const history = await chatApi.sessionMessages(targetSessionId, 50)
      if (Array.isArray(history) && history.length > 0) {
        messages.value = history.map((item, idx) => ({
          id: item.id ? `msg_hist_${item.id}` : `msg_hist_${idx}_${Date.now()}`,
          role: item.role === 'user' ? 'user' : 'assistant',
          text: item.content || item.text || '',
          timestamp: item.createdAt ? new Date(item.createdAt).toLocaleTimeString() : (item.created_at || new Date().toLocaleTimeString()),
          displayBlocks: item.displayBlocks || item.display_blocks || [],
          traceId: item.agent_trace_id || item.traceId,
          responseType: item.responseType || (item.intent === 'CLARIFY_NEEDED' ? 'CLARIFY' : (item.intent === 'PLAN_RECOMMENDATION' ? 'PLAN_RECOMMENDATION' : 'ANSWER')),
          missingSlots: item.missingSlots || [],
          confirmFields: item.confirmFields || [],
          clarifyQuestion: item.clarifyQuestion || (item.intent === 'CLARIFY_NEEDED' ? (item.content || item.text) : undefined),
        }))

        // Restore latest traceId if any
        const lastWithTrace = [...history].reverse().find(m => m.agent_trace_id || m.traceId)
        if (lastWithTrace) {
          latestTraceId.value = lastWithTrace.agent_trace_id || lastWithTrace.traceId
        } else if (!isSameSession) {
          latestTraceId.value = null
        }
      }

      if (messages.value.length === 0) {
        messages.value.push({
          id: `msg_welcome_${Date.now()}`,
          role: 'assistant',
          text: WELCOME_TEXT,
          timestamp: new Date().toLocaleTimeString(),
        })
      }
    } catch (err: any) {
      console.warn('[ChatStore] Failed to load session messages:', err)
      messages.value.push({
        id: `msg_welcome_${Date.now()}`,
        role: 'assistant',
        text: WELCOME_TEXT,
        timestamp: new Date().toLocaleTimeString(),
      })
    }
  }

  // Create a new session
  async function createNewSession() {
    try {
      const res = await chatApi.createSession()
      const newSessId = res.sessionId
      sessionId.value = newSessId
      latestTraceId.value = null
      messages.value = [
        {
          id: `msg_welcome_${Date.now()}`,
          role: 'assistant',
          text: WELCOME_TEXT,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]

      // Prepend to list
      const newItem: SessionItem = {
        sessionId: newSessId,
        title: '新出行规划会话',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messageCount: 0,
      }
      sessionList.value.unshift(newItem)
      return newSessId
    } catch (err: any) {
      ElMessage.error(`创建新会话失败: ${err.message}`)
      throw err
    }
  }

  // Delete a session
  async function deleteSession(targetSessionId: string) {
    try {
      await sessionApi.deleteSession(targetSessionId)
      sessionList.value = sessionList.value.filter(s => s.sessionId !== targetSessionId)
      ElMessage.success('会话已删除')

      if (sessionId.value === targetSessionId) {
        if (sessionList.value.length > 0) {
          await switchSession(sessionList.value[0].sessionId)
        } else {
          await createNewSession()
        }
      }
    } catch (err: any) {
      ElMessage.error(`删除会话失败: ${err.message}`)
    }
  }

  // Rename a session
  async function renameSession(targetSessionId: string, newTitle: string) {
    const trimmed = newTitle.trim()
    if (!trimmed) return
    try {
      await sessionApi.updateSessionTitle(targetSessionId, trimmed)
      const found = sessionList.value.find(s => s.sessionId === targetSessionId)
      if (found) {
        found.title = trimmed
      }
      ElMessage.success('会话标题已更新')
    } catch (err: any) {
      ElMessage.error(`更新标题失败: ${err.message}`)
    }
  }

  // Initialize session and restore messages
  async function initSession(forceNew = false) {
    await loadSessionList()

    if (forceNew) {
      await createNewSession()
      return
    }

    if (sessionList.value.length > 0) {
      // Find current or first
      const target = sessionList.value.find(s => s.sessionId === sessionId.value) || sessionList.value[0]
      await switchSession(target.sessionId)
    } else {
      await createNewSession()
    }
  }

  // Send user message
  async function sendMessage(text: string) {
    const trimmed = text.trim()
    if (!trimmed || isSending.value) return

    if (!sessionId.value) {
      await initSession()
    }

    // Auto title generation if this is the first message or default title
    const currentItem = sessionList.value.find(s => s.sessionId === sessionId.value)
    if (currentItem && (currentItem.title === '新出行规划会话' || currentItem.title === '新会话' || !currentItem.title)) {
      const autoTitle = trimmed.length > 20 ? trimmed.slice(0, 20) + '...' : trimmed
      currentItem.title = autoTitle
      sessionApi.updateSessionTitle(sessionId.value, autoTitle).catch(() => {})
    }

    const userMsgId = `msg_user_${Date.now()}`
    messages.value.push({
      id: userMsgId,
      role: 'user',
      text: trimmed,
      timestamp: new Date().toLocaleTimeString(),
    })

    isSending.value = true

    try {
      const resp = await chatApi.chat({
        sessionId: sessionId.value,
        message: trimmed,
      })

      if (resp.sessionId) {
        sessionId.value = resp.sessionId
      }
      if (resp.traceId) {
        latestTraceId.value = resp.traceId
      }
      if (resp.taskId) {
        activeTaskId.value = resp.taskId
      }

      const assistantMsgId = `msg_ast_${Date.now()}`
      messages.value.push({
        id: assistantMsgId,
        role: 'assistant',
        text: resp.speechText || '',
        timestamp: new Date().toLocaleTimeString(),
        traceId: resp.traceId,
        responseType: resp.responseType,
        displayBlocks: resp.displayBlocks || [],
        missingSlots: resp.missingSlots || [],
        confirmFields: resp.confirmFields || [],
        clarifyQuestion: resp.clarifyQuestion,
        taskId: resp.taskId,
        orderNo: resp.orderNo,
      })

      if (currentItem) {
        currentItem.messageCount = (currentItem.messageCount || 0) + 2
        currentItem.updatedAt = new Date().toISOString()
      }
    } catch (err: any) {
      console.error('[ChatStore] sendMessage error:', err)
      messages.value.push({
        id: `msg_err_${Date.now()}`,
        role: 'system',
        text: `发送失败：${err.message || '网络异常'}`,
        timestamp: new Date().toLocaleTimeString(),
      })
    } finally {
      isSending.value = false
    }
  }

  // Submit feedback on plan or trip
  async function submitFeedback(
    messageId: string,
    payload: {
      planId?: string
      traceId?: string
      action: string
      rating: number
      reason?: string
      orderNo?: string
    }
  ) {
    try {
      await chatApi.saveFeedback({
        ...payload,
        sessionId: sessionId.value,
      })
      const target = messages.value.find((m) => m.id === messageId)
      if (target) {
        target.feedbackSaved = true
        target.feedbackRating = payload.rating
      }
      ElMessage.success('反馈已记录，已计入 Agent 质量评估！')
    } catch (err: any) {
      ElMessage.error(`反馈保存失败：${err.message}`)
    }
  }

  // Handle SSE pushed updates
  function handleSSEMessage(data: any) {
    if (!data) return

    // 1. Task progress update
    if (data.kind === 'TASK_PROGRESS' || data.task_progress) {
      const progress = data.task_progress || data
      const taskId = progress.taskId || data.taskId
      if (taskId) {
        activeTaskId.value = taskId
      }
      const matched = messages.value.slice().reverse().find((m) => m.taskId === taskId)
      if (matched) {
        matched.text = progress.message || progress.step || matched.text
        if (progress.status) {
          matched.responseType = 'TASK_PROGRESS'
        }
      } else if (data.text) {
        messages.value.push({
          id: `msg_sse_task_${Date.now()}`,
          role: 'assistant',
          text: data.text,
          timestamp: new Date().toLocaleTimeString(),
          taskId: taskId,
          responseType: 'TASK_PROGRESS',
        })
      }
    }

    // 2. Image (Payment QR Code push)
    if (data.kind === 'IMAGE' || data.image_path) {
      messages.value.push({
        id: `msg_sse_img_${Date.now()}`,
        role: 'assistant',
        text: data.text || '支付二维码已送达：',
        timestamp: new Date().toLocaleTimeString(),
        displayBlocks: [
          {
            type: 'IMAGE',
            imagePath: data.image_path || '/media/qr_code.jpg',
            title: data.text || '支付二维码',
          },
        ],
      })
    }

    // 3. Price drop alert
    if (data.event_type === 'PRICE_DROP_NOTIFIED' || data.event_type === 'PRICE_DROP_DETECTED') {
      messages.value.push({
        id: `msg_sse_price_${Date.now()}`,
        role: 'assistant',
        text: `【降价提醒】为您监控的行程发现降价！${data.text || ''}`,
        timestamp: new Date().toLocaleTimeString(),
        displayBlocks: data.blocks || [],
      })
    }
  }

  // Subscribe to SSE events
  sseService.on('*', handleSSEMessage)

  return {
    sessionId,
    sessionList,
    isLoadingSessions,
    isSidebarCollapsed,
    messages,
    isSending,
    activeTaskId,
    latestTraceId,
    toggleSidebar,
    loadSessionList,
    switchSession,
    createNewSession,
    deleteSession,
    renameSession,
    initSession,
    sendMessage,
    submitFeedback,
    handleSSEMessage,
  }
})
