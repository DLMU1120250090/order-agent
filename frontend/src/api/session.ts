import { apiClient } from './client'
import type { SessionItem } from '@/types/chat'

export const sessionApi = {
  createSession: () => apiClient.post<{ sessionId: string }>('/sessions'),
  listSessions: (limit = 50) => apiClient.get<SessionItem[]>('/sessions', { params: { limit } }),
  deleteSession: (sessionId: string) => apiClient.delete<{ ok: boolean }>(`/sessions/${encodeURIComponent(sessionId)}`),
  updateSessionTitle: (sessionId: string, title: string) =>
    apiClient.put<{ ok: boolean; sessionId: string; title: string }>(`/sessions/${encodeURIComponent(sessionId)}`, { title }),
  getSessionMessages: (sessionId: string, limit = 50) =>
    apiClient.get<any[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`, { params: { limit } }),
}
