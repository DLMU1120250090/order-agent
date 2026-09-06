export interface TravelOrder {
  id: number
  orderNo: string
  userId: number
  channel: string
  status: 'CREATED' | 'LOCKED' | 'PAID' | 'CANCELLED' | 'REFUNDED' | 'CHANGED' | string
  tripId?: number
  planId?: string
  totalPrice: number
  legs: any[]
  passengers: any[]
  checklist?: string[]
  createdAt: string
  updatedAt: string
}
