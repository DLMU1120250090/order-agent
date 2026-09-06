import { useUserStore } from '@/stores/user'

type SSECallback = (event: any) => void

class SSEService {
  private source: EventSource | null = null
  private listeners: Map<string, Set<SSECallback>> = new Map()
  private currentUserId: number | null = null
  private reconnectTimer: any = null
  private retryCount = 0

  connect(force = false) {
    const userStore = useUserStore()
    const userId = userStore.userId

    if (this.source && this.currentUserId === userId && !force) {
      return
    }

    this.disconnect()
    this.currentUserId = userId

    const url = `/api/v1/travel/events?userId=${encodeURIComponent(userId)}`
    try {
      this.source = new EventSource(url)

      this.source.onopen = () => {
        this.retryCount = 0
        console.log(`[SSE] Connected for user ${userId}`)
      }

      this.source.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data)
          this.emit('*', payload)
          if (payload.kind) {
            this.emit(payload.kind, payload)
          }
          if (payload.event_type) {
            this.emit(payload.event_type, payload)
          }
        } catch (err) {
          console.warn('[SSE] Parse message error:', err, e.data)
        }
      }

      this.source.onerror = (err) => {
        console.warn('[SSE] Connection error:', err)
        this.disconnect()
        this.scheduleReconnect()
      }
    } catch (e) {
      console.error('[SSE] Failed to establish connection:', e)
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return
    const delay = Math.min(30000, 1000 * Math.pow(1.5, this.retryCount))
    this.retryCount++
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect(true)
    }, delay)
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.source) {
      this.source.close()
      this.source = null
    }
  }

  on(event: string, callback: SSECallback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(callback)
    return () => this.off(event, callback)
  }

  off(event: string, callback: SSECallback) {
    this.listeners.get(event)?.delete(callback)
  }

  private emit(event: string, data: any) {
    this.listeners.get(event)?.forEach((cb) => {
      try {
        cb(data)
      } catch (err) {
        console.error(`[SSE] Listener error on ${event}:`, err)
      }
    })
  }
}

export const sseService = new SSEService()
