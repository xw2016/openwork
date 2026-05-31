// 合约相关 API
import http from './index'
import type { Contract, Deliverable, PaginatedResponse } from '@/types'

/** 创建合约（雇主发布任务） */
export function createContract(data: Partial<Contract>) {
  return http.post<Contract>('/v1/contracts', data)
}

/** 获取合约列表 */
export function getMyContracts(params?: { page?: number; page_size?: number; status?: string }) {
  return http.get<PaginatedResponse<Contract>>('/v1/contracts', { params })
}

/** 获取合约详情 */
export function getContractDetail(contractId: string) {
  return http.get<Contract>(`/v1/contracts/${contractId}`)
}

/** 更新合约 */
export function updateContract(contractId: string, data: Partial<Contract>) {
  return http.put<Contract>(`/v1/contracts/${contractId}`, data)
}

/** 发布合约 */
export function publishContract(contractId: string) {
  return http.post(`/v1/contracts/${contractId}/publish`)
}

/** 接受合约（自由职业者） */
export function acceptContract(contractId: string) {
  return http.post(`/v1/contracts/${contractId}/accept`)
}

/** 提交交付物 */
export function submitDeliverable(contractId: string, deliverableId: string) {
  return http.post(`/v1/contracts/${contractId}/submit`, { deliverable_id: deliverableId })
}

/** 完成合约 */
export function completeContract(contractId: string) {
  return http.post(`/v1/contracts/${contractId}/complete`)
}

/** 终止合约 */
export function terminateContract(contractId: string) {
  return http.post(`/v1/contracts/${contractId}/terminate`)
}

/** 获取合约交付物列表 */
export function getDeliverables(contractId: string) {
  return http.get<Deliverable[]>(`/v1/contracts/${contractId}/deliverables`)
}

/** 创建交付物 */
export function createDeliverable(contractId: string, data: Partial<Deliverable>) {
  return http.post<Deliverable>(`/v1/contracts/${contractId}/deliverables`, data)
}
