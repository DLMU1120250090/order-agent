import { apiClient } from './client'
import type { EvaluationRequest, EvaluationReport } from '@/types/evaluation'

export const evaluationApi = {
  runEvaluation: (payload: EvaluationRequest) =>
    apiClient.post<EvaluationReport>('/evaluations', payload),
}
