import { apiClient } from './client'
import type { TravelOrder } from '@/types/order'

export const orderApi = {
  listOrders: () => apiClient.get<TravelOrder[]>('/orders'),
  getOrder: (orderNo: string) => apiClient.get<TravelOrder>(`/orders/${encodeURIComponent(orderNo)}`),
}
