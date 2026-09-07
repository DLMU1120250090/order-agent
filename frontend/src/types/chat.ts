export type MessageRole = 'user' | 'assistant' | 'system'

export interface PlanLeg {
  mode: string
  vehicle_no?: string
  from_station?: string
  to_station?: string
  from_city?: string
  to_city?: string
  depart: string
  arrive: string
  price: number
  seat?: string
  carrier?: string
  arrive_day?: number
}

export interface PlanOption {
  planId?: string
  plan_id?: string
  planNo?: number
  mode?: 'TRAIN' | 'FLIGHT' | 'MIXED'
  legs: PlanLeg[]
  totalPrice?: number
  total_price?: number
  totalDurationH?: number
  total_duration_h?: number
  score?: number
  meetsBudget?: boolean
  reason?: string
  summary?: string
}

export interface OrderBlockItem {
  orderNo: string
  type: string
  status: string
  price: number
  tripDate?: string
  legs?: PlanLeg[]
}

export interface ClarifySlotOption {
  slot: string
  label: string
  options: string[]
}

export interface ChatMessage {
  id: string
  role: MessageRole
  text: string
  timestamp: string
  traceId?: string
  responseType?: 'ANSWER' | 'CLARIFY' | 'TASK_PROGRESS'
  displayBlocks?: any[]
  missingSlots?: string[]
  clarifyQuestion?: string
  taskId?: string
  orderNo?: string
  feedbackSaved?: boolean
  feedbackRating?: number
}

export interface TravelChatRequest {
  sessionId?: string
  message: string
  channel?: string
}

export interface TravelChatResponse {
  sessionId: string
  traceId?: string
  responseType: 'ANSWER' | 'CLARIFY' | 'TASK_PROGRESS'
  speechText: string
  displayBlocks: any[]
  nextAction: string
  clarifyQuestion?: string
  missingSlots: string[]
  taskId?: string
  orderNo?: string
}

export interface SessionItem {
  sessionId: string
  title: string
  phase?: string
  createdAt?: string
  updatedAt?: string
  messageCount?: number
}
