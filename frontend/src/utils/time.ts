/**
 * 解析时间输入并智能兼容处理 UTC 与带时区时间串
 * 若无时区标记者，按系统历史存入的 naive UTC 规范，自动补 'Z' 进行 UTC 解析
 */
export function parseUtcDate(s?: string | Date | null): Date | null {
  if (!s) return null
  if (s instanceof Date) return isNaN(s.getTime()) ? null : s
  let norm = String(s).trim()
  if (!norm) return null
  // 若无时区标识（'Z', '+', '-' 尾部），后端历史存入的均为 naive UTC 时间，因此追加 'Z' 确保按 UTC 解析
  if (!norm.endsWith('Z') && !/[+-]\d{2}(:\d{2})?$/.test(norm)) {
    norm = norm + 'Z'
  }
  const d = new Date(norm)
  return isNaN(d.getTime()) ? null : d
}

/**
 * 格式化为北京时间完整日期时间：YYYY/M/D HH:mm:ss
 */
export function formatBeijingDateTime(s?: string | Date | null): string {
  const d = parseUtcDate(s)
  if (!d) return typeof s === 'string' && s ? s : '-'
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

/**
 * 格式化为北京时间时分秒：HH:mm:ss
 */
export function formatBeijingTime(s?: string | Date | null): string {
  const d = parseUtcDate(s)
  if (!d) return typeof s === 'string' && s ? s : '-'
  return d.toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
