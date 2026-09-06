export interface TraceEvaluationResult {
  traceId: string
  sessionId: string
  createdAt: string
  score?: number
  ruleScore?: number
  llmJudgeScore?: number
  userFeedbackScore?: number
  metrics: Record<string, number | null>
  detail: Record<string, any>
}

export interface EvaluationReport {
  startAt: string
  endAt: string
  totalTraces: number
  totalLinks?: number
  labeledTraces: number
  avgScore?: number
  metricAverages: Record<string, number | null>
  failureDistribution: Record<string, number>
  traceResults: TraceEvaluationResult[]
  linkResults?: TraceEvaluationResult[]
}

export interface EvaluationRequest {
  startAt: string
  endAt: string
  includeLlmJudge?: boolean
  limit?: number
}
