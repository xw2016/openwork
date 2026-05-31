// 市场相关 API 桩
import http from './index'
import type { Contract, PaginatedResponse } from '@/types'

/** 获取任务列表（自由职业者视角） */
export function getMarketTasks(params?: { page?: number; page_size?: number }) {
  return http.get<PaginatedResponse<Contract>>('/v1/market/tasks', { params })
}

/** 获取任务详情 */
export function getTaskDetail(taskId: string) {
  return http.get<Contract>(`/v1/market/tasks/${taskId}`)
}

/** 接受任务 */
export function acceptTask(taskId: string) {
  return http.post<Contract>(`/v1/market/tasks/${taskId}/accept`)
}
