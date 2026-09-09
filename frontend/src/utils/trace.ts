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
