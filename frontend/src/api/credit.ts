// 信用评分 API
import http from './index'

/** 信用分详情 */
export interface CreditScore {
  score: number
  level: string
  breakdown: {
    completion_rate: number
    on_time_rate: number
    acceptance_rate: number
    dispute_rate: number
  }
}

/** 信用历史记录 */
export interface CreditHistoryItem {
  id: string
  change: number
  reason: string
  contract_id: string | null
  created_at: string
}

/** 获取当前用户信用分 */
export function getMyScore() {
  return http.get<CreditScore>('/v1/credit/score')
}

/** 获取信用历史 */
export function getCreditHistory(params?: { page?: number; page_size?: number }) {
  return http.get<{ items: CreditHistoryItem[]; total: number }>('/v1/credit/history', { params })
}

/** 刷新信用分 */
export function refreshCreditScore() {
  return http.post<CreditScore>('/v1/credit/refresh')
}

/** 获取指定用户信用分 */
export function getUserScore(userId: string) {
  return http.get<CreditScore>(`/v1/credit/users/${userId}/score`)
}
