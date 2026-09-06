import { apiClient } from './client'
import type { UserProfile, TripEpisode, DistillReport } from '@/types/memory'

export const memoryApi = {
  getProfile: () => apiClient.get<UserProfile>('/profiles'),
  updateProfile: (payload: Partial<UserProfile>) => apiClient.put<UserProfile>('/profiles', payload),
  listEpisodes: (limit = 20) => apiClient.get<TripEpisode[]>('/memory/episodes', { params: { limit } }),
  getDistillReport: () => apiClient.get<DistillReport>('/memory/distill'),
  triggerDistill: () => apiClient.post<DistillReport>('/memory/distill'),
}
