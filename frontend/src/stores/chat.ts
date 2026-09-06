import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi } from '@/api/chat'
import { sseService } from '@/services/sse'
import type { ChatMessage, TravelChatResponse } from '@/types/chat'
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
  const messages = ref<ChatMessage[]>([])
  const isSending = ref<boolean>(false)
  const activeTaskId = ref<string | null>(null)
  const latestTraceId = ref<string | null>(null)

  // Initialize session and restore messages
  async function initSession(forceNew = false) {
    if (sessionId.value && !forceNew && messages.value.length > 0) {
      return
    }

    try {
      if (forceNew) {
        const res = await chatApi.createSession()
        sessionId.value = res.sessionId
        messages.value = []
      } else {
        try {
          const res = await chatApi.latestSession()
          sessionId.value = res.sessionId
        } catch {
          const created = await chatApi.createSession()
          sessionId.value = created.sessionId
        }
      }

      // Load history
      if (!forceNew && sessionId.value) {
        try {
          const history = await chatApi.sessionMessages(sessionId.value, 30)
          if (Array.isArray(history) && history.length > 0) {
            messages.value = history.map((item, idx) => ({
              id: `msg_hist_${idx}_${Date.now()}`,
              role: item.role === 'user' ? 'user' : 'assistant',
              text: item.content || item.text || '',
              timestamp: item.created_at || new Date().toLocaleTimeString(),
              displayBlocks: item.display_blocks || item.displayBlocks || [],
            }))
          }
        } catch (e) {
          console.warn('[ChatStore] Failed to restore history messages:', e)
        }
      }

      // If still empty, add welcome message
      if (messages.value.length === 0) {
        messages.value.push({
          id: `msg_welcome_${Date.now()}`,
          role: 'assistant',
          text: WELCOME_TEXT,
          timestamp: new Date().toLocaleTimeString(),
        })
      }
    } catch (err: any) {
      console.error('[ChatStore] initSession error:', err)
      ElMessage.error(err.message || '初始化会话失败')
    }
  }

  // Send user message
  async function sendMessage(text: string) {
    const trimmed = text.trim()
    if (!trimmed || isSending.value) return

    if (!sessionId.value) {
      await initSession()
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
        clarifyQuestion: resp.clarifyQuestion,
        taskId: resp.taskId,
        orderNo: resp.orderNo,
      })
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
      // Check if there is an active message with matching taskId
      const matched = messages.value.slice().reverse().find((m) => m.taskId === taskId)
      if (matched) {
        matched.text = progress.message || progress.step || matched.text
        if (progress.status) {
          matched.responseType = 'TASK_PROGRESS'
        }
      } else if (data.text) {
        // Append progress notice if substantial
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
    messages,
    isSending,
    activeTaskId,
    latestTraceId,
    initSession,
    sendMessage,
    submitFeedback,
    handleSSEMessage,
  }
})
