export interface Passenger {
  passenger_id: string
  role?: string
  name?: string
  id_type?: string
  id_no?: string
  id_expiry?: string
  [key: string]: any
}

export interface UserProfile {
  user_id: number
  home_city?: string
  passengers: Passenger[]
  budget_level?: string
  preferences: Record<string, any>
  preferences_v2: {
    user?: Record<string, any>
    passengers?: Record<string, Record<string, any>>
    [key: string]: any
  }
}

export interface TripEpisode {
  id: number
  tripId?: number
  summaryMd: string
  episode: {
    trip_id?: number
    user_id?: number
    passengers?: string[]
    context?: {
      origin?: string
      destination?: string
      purpose?: string
    }
    constraints?: Record<string, any>
    selected_plan?: {
      mode?: string
      depart?: string
      price?: number
      order_no?: string
      [key: string]: any
    }
    decision_reason?: any[]
    outcome?: {
      booking_success?: boolean
      rating?: number
      [key: string]: any
    }
    [key: string]: any
  }
  createdAt?: string
}

export interface DistillReport {
  userId: number
  content: string
  preferencesV2?: {
    user?: Record<string, any>
    passengers?: Record<string, Record<string, any>>
    [key: string]: any
  }
}

export interface UserMemoryEvent {
  id: number
  userId: number
  eventType: string
  sessionId?: string
  taskId?: string
  traceId?: string
  orderNo?: string
  context?: Record<string, any>
  result?: Record<string, any>
  createdAt?: string
}
