export interface TravelOrder {
  id?: number
  orderNo?: string
  order_no?: string
  userId?: number
  channel?: string
  supplier?: string
  type?: string
  status: 'CREATED' | 'LOCKED' | 'PAID' | 'CANCELLED' | 'REFUNDED' | 'CHANGED' | string
  tripId?: number
  planId?: string
  totalPrice?: number
  price?: number
  tax_fee?: number
  legs: any[]
  passengers: any[]
  checklist?: string[]
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
  tripDate?: string
  trip_date?: string
  qr_image_path?: string | null
  pending?: string | null
}
