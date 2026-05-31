// 市场相关 API
import http from './index'
import type { Contract, PaginatedResponse } from '@/types'

/** 获取任务列表（自由职业者视角） */
export function getMarketTasks(params?: { page?: number; page_size?: number; category?: string; min_budget?: number; max_budget?: number; status?: string }) {
  return http.get<PaginatedResponse<Contract>>('/v1/market/tasks', { params })
}

/** 获取任务详情 */
export function getTaskDetail(taskId: string) {
  return http.get<Contract>(`/v1/market/tasks/${taskId}`)
}

/** 竞标/接单 */
export function bidTask(taskId: string, data?: { proposal?: string; price?: number }) {
  return http.post(`/v1/market/tasks/${taskId}/bid`, data)
}

/** 提交交付物（市场入口） */
export function submitMarketDeliverable(taskId: string, deliverableId: string) {
  return http.post(`/v1/market/tasks/${taskId}/deliverables/${deliverableId}/submit`)
}
