import { apiClient } from './client'
import type { TraceRowOut, TraceFilterParams, TraceLabelRequest } from '@/types/trace'

export const traceApi = {
  listTraces: (params?: TraceFilterParams) => apiClient.get<TraceRowOut[]>('/debug/traces', { params }),
  getTrace: (traceId: string) => apiClient.get<TraceRowOut>(`/debug/traces/${encodeURIComponent(traceId)}`),
  listSessionTraces: (sessionId: string, limit = 50) =>
    apiClient.get<TraceRowOut[]>(`/debug/sessions/${encodeURIComponent(sessionId)}/traces`, { params: { limit } }),
  replayTrace: (traceId: string) => apiClient.post('/debug/replay', { traceId }),
  labelTrace: (traceId: string, payload: TraceLabelRequest) =>
    apiClient.put(`/debug/traces/${encodeURIComponent(traceId)}/label`, payload),
}
