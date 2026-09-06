export interface TraceEvent {
  stepOrder: number
  eventType: string
  phase: string
  eventId?: string
  parentEventId?: string
  runId?: string
  taskId?: string
  agentName?: string
  modelName?: string
  toolName?: string
  inputPayload?: string
  outputPayload?: string
  latencyMs?: number
  inputTokens?: number
  outputTokens?: number
  totalTokens?: number
  errorMessage?: string
  errorType?: string
  errorRecoverable?: boolean
  retryNo?: number
  decision?: Record<string, any>
  stateBefore?: any
  stateAfter?: any
  memorySources?: string[]
  memoryIds?: string[]
  memoryVersion?: string
  inferredFields?: Record<string, any>
  createdAt?: string
}

export interface TraceRowOut {
  traceId: string
  sessionId: string
  userId: number
  status: 'SUCCESS' | 'FAILED' | string
  eventCount: number
  durationMs?: number
  errorMessage?: string
  runId?: string
  taskId?: string
  traceJson: {
    traceId?: string
    events?: TraceEvent[]
    [key: string]: any
  } | TraceEvent[]
  createdAt: string
  updatedAt: string
  expectedIntent?: string
  expectedSlots?: Record<string, any>
  expectedClarifyAction?: string
  labeledBy?: number
  labeledAt?: string
  labelNote?: string
}

export interface TraceFilterParams {
  startAt?: string
  endAt?: string
  onlyUnlabeled?: boolean
  taskId?: string
  runId?: string
  limit?: number
  sessionId?: string
}

export interface TraceLabelRequest {
  expectedIntent?: string
  expectedSlots?: Record<string, any>
  expectedClarifyAction?: string
  labelNote?: string
}
