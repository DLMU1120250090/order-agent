import { apiClient } from './client'
import type { TravelChatRequest, TravelChatResponse } from '@/types/chat'

export const chatApi = {
  createSession: () => apiClient.post<{ sessionId: string }>('/sessions'),
  latestSession: () => apiClient.get<{ sessionId: string }>('/sessions/latest'),
  chat: (payload: TravelChatRequest) => apiClient.post<TravelChatResponse>('/chat', payload),
  sessionMessages: (sessionId: string, limit = 50) =>
    apiClient.get<any[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`, { params: { limit } }),
  saveFeedback: (payload: {
    planId?: string
    traceId?: string
    action: string
    rating: number
    reason?: string
    sessionId?: string
    orderNo?: string
  }) => apiClient.post('/feedback', payload),
}
