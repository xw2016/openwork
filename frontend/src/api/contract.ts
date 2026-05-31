// 合约相关 API 桩
import http from './index'
import type { Contract, Deliverable } from '@/types'

/** 创建合约（雇主发布任务） */
export function createContract(data: Partial<Contract>) {
  return http.post<Contract>('/v1/contracts', data)
}

/** 获取雇主的合约列表 */
export function getMyContracts() {
  return http.get<Contract[]>('/v1/contracts/mine')
}

/** 获取合约详情 */
export function getContractDetail(contractId: string) {
  return http.get<Contract>(`/v1/contracts/${contractId}`)
}

/** 获取合约的交付物列表 */
export function getDeliverables(contractId: string) {
  return http.get<Deliverable[]>(`/v1/contracts/${contractId}/deliverables`)
}
