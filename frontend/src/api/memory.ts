import { apiClient } from './client'
import type { UserProfile, TripEpisode, DistillReport, UserMemoryEvent } from '@/types/memory'

export const memoryApi = {
  getProfile: () => apiClient.get<UserProfile>('/profiles'),
  updateProfile: (payload: Partial<UserProfile>) => apiClient.put<UserProfile>('/profiles', payload),
  addPassenger: (passenger: { name: string; id_no: string; id_type?: string; role?: string; age_group?: string }) =>
    apiClient.post<UserProfile>('/profiles/passengers', passenger),
  updatePassenger: (passengerId: string, payload: { name?: string; id_no?: string; id_type?: string; role?: string; age_group?: string; seat_need?: string }) =>
    apiClient.put<UserProfile>(`/profiles/passengers/${passengerId}`, payload),
  deletePassenger: (passengerId: string) =>
    apiClient.delete<UserProfile>(`/profiles/passengers/${passengerId}`),
  listEpisodes: (limit = 50) => apiClient.get<TripEpisode[]>('/memory/episodes', { params: { limit } }),
  listUserEvents: (limit = 50) => apiClient.get<UserMemoryEvent[]>('/memory/events', { params: { limit } }),
  getDistillReport: () => apiClient.get<DistillReport>('/memory/distill'),
  triggerDistill: () => apiClient.post<DistillReport>('/memory/distill'),
}
