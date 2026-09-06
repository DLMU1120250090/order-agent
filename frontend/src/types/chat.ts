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
}

export interface PlanOption {
  plan_id: string
  mode: 'TRAIN' | 'FLIGHT' | 'MIXED'
  legs: PlanLeg[]
  total_price: number
  total_duration_h: number
  score: number
  reason?: string
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
