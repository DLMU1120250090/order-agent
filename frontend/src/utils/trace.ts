import type { TraceRowOut } from '@/types/trace'

/**
 * 从 Trace 实体中提取关联的订单号集合 (匹配 ORD 格式，如 ORD2026090912040301)
 */
export function extractOrderNos(trace: TraceRowOut): string[] {
  if (!trace) return []
  const orderNos: string[] = []

  // 1. 优先从 task_id / run_id 检查
  if (trace.taskId && trace.taskId.includes('ORD')) {
    const m = trace.taskId.match(/ORD\d{14,20}/g)
    if (m) orderNos.push(...m)
  }
  if (trace.runId && trace.runId.includes('ORD')) {
    const m = trace.runId.match(/ORD\d{14,20}/g)
    if (m) orderNos.push(...m)
  }

  // 2. 从 traceJson 序列化内容全面扫描
  if (trace.traceJson) {
    const str = typeof trace.traceJson === 'string' ? trace.traceJson : JSON.stringify(trace.traceJson)
    const matches = str.match(/ORD\d{14,20}/g)
    if (matches) {
      orderNos.push(...matches)
    }
  }

  return Array.from(new Set(orderNos))
}

/**
 * 提取主订单号（首个或唯一订单号）
 */
export function getPrimaryOrderNo(trace: TraceRowOut): string | null {
  const list = extractOrderNos(trace)
  return list.length > 0 ? list[0] : null
}

/**
 * 格式化会话/ID 为简短易读字符串
 */
export function formatShortId(id?: string, maxLen = 14): string {
  if (!id) return '-'
  if (id.length <= maxLen) return id
  return id.slice(0, maxLen) + '...'
}

/**
 * 统一意图字典表与中文标签
 */
export const INTENT_LABELS: Record<string, string> = {
  PLAN_RECOMMENDATION: '出行方案推荐',
  CLARIFY_NEEDED: '信息不足追问',
  PLAN_ADJUST: '调整方案',
  PLAN_BOOK: '确认下单',
  ORDER_QUERY: '查订单',
  ORDER_CHANGE: '改签申请',
  ORDER_CANCEL: '取消/退票',
  PRICE_MONITOR: '价格监控',
  CHECKLIST_EXPORT: '清单导出',
  OTHER: '闲聊/其他',
}

export function formatIntentName(intent?: string): string {
  if (!intent) return '未识别/系统任务'
  const label = INTENT_LABELS[intent]
  return label ? `${label} (${intent})` : intent
}

export interface TraceSnapshot {
  userMessage?: string
  actualIntent?: string
  actualClarifyAction?: string
  actualSlots: {
    departure?: string
    destination?: string
    departureDate?: string
    transportPreference?: string
    [key: string]: any
  }
}

/**
 * 从 Trace 事件列表中提取当前请求的运行时实际快照：
 * 包含：用户原话、大模型识别意图、澄清决策、抽取槽位
 */
export function extractTraceSnapshot(events: any[]): TraceSnapshot {
  let userMessage = ''
  let actualIntent = ''
  let actualClarifyAction = ''
  const actualSlots: Record<string, any> = {}

  if (!Array.isArray(events)) {
    return { actualSlots }
  }

  for (const ev of events) {
    if (!ev) continue

    const parsePayload = (val: any) => {
      if (!val) return null
      if (typeof val === 'object') return val
      try {
        return JSON.parse(val)
      } catch {
        return val
      }
    }

    const inp = parsePayload(ev.inputPayload)
    const out = parsePayload(ev.outputPayload)

    // 1. 提取用户原话
    if (!userMessage) {
      if (ev.eventType === 'REQUEST_RECEIVED') {
        if (inp && typeof inp === 'object' && inp.text) {
          userMessage = inp.text
        } else if (typeof inp === 'string' && inp.trim()) {
          userMessage = inp.trim()
        }
      } else if (ev.eventType === 'USER_MESSAGE_RECORDED') {
        if (typeof inp === 'string' && inp.trim()) {
          userMessage = inp.trim()
        } else if (inp && typeof inp === 'object' && inp.text) {
          userMessage = inp.text
        }
      }
    }

    // 2. 提取识别意图（REVISED 优先，其次 RECOGNIZED/FALLBACK）
    if (ev.eventType === 'INTENT_REVISED' && out && typeof out === 'object' && out.intent) {
      actualIntent = out.intent
    } else if (!actualIntent && (ev.eventType === 'INTENT_RECOGNIZED' || ev.eventType === 'INTENT_FALLBACK') && out && typeof out === 'object' && out.intent) {
      actualIntent = out.intent
    }

    // 3. 提取澄清决策
    if (ev.eventType === 'CLARIFY_DECISION' && out && typeof out === 'object') {
      actualClarifyAction = out.action || actualClarifyAction
    }

    // 4. 提取槽位（SLOTS_MERGED 优先，其次 INTENT_REVISED/RECOGNIZED）
    if (ev.eventType === 'SLOTS_MERGED' && out && typeof out === 'object') {
      Object.assign(actualSlots, out)
    } else if ((ev.eventType === 'INTENT_REVISED' || ev.eventType === 'INTENT_RECOGNIZED') && out && typeof out === 'object' && out.slots) {
      Object.assign(actualSlots, out.slots)
    }
  }

  const getSlotVal = (keys: string[]) => {
    for (const k of keys) {
      const v = actualSlots[k]
      if (Array.isArray(v) && v.length > 0) return String(v[0])
      if (typeof v === 'string' && v.trim()) return v.trim()
    }
    return ''
  }

  return {
    userMessage,
    actualIntent,
    actualClarifyAction,
    actualSlots: {
      departure: getSlotVal(['origin', 'departure', 'fromCity']),
      destination: getSlotVal(['destination', 'toCity']),
      departureDate: getSlotVal(['tripDate', 'departureDate', 'date']),
      transportPreference: getSlotVal(['transportMode', 'preferred_transport', 'transportPreference']),
      ...actualSlots,
    },
  }
}

/**
 * 快速从单个 TraceRowOut 中提取意图信息（供列表卡片展示）
 */
export function getTraceQuickIntent(trace: TraceRowOut): string {
  if (!trace || !trace.traceJson) return ''
  const str = typeof trace.traceJson === 'string' ? trace.traceJson : JSON.stringify(trace.traceJson)
  
  // 匹配 "intent":"PLAN_RECOMMENDATION" 等
  const m = str.match(/"intent"\s*:\s*"([A-Z_]+)"/)
  if (m && m[1] && m[1] !== 'INTENT_FALLBACK') {
    return m[1]
  }
  return ''
}
