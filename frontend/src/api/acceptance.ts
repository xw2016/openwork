// 验收相关 API
import http from './index'
import type { AcceptanceRecord } from '@/types'

/** 触发 AI 验收 */
export function triggerAcceptance(contractId: string) {
  return http.post<AcceptanceRecord>(`/v1/acceptance/contracts/${contractId}/evaluate`)
}

/** 获取合约验收记录列表 */
export function getAcceptanceRecords(contractId: string) {
  return http.get<AcceptanceRecord[]>(`/v1/acceptance/contracts/${contractId}/records`)
}

/** 获取单条验收记录详情 */
export function getAcceptanceDetail(recordId: string) {
  return http.get<AcceptanceRecord>(`/v1/acceptance/records/${recordId}`)
}

/** 驳回交付物（雇主） */
export function rejectDeliverable(deliverableId: string, data: { reason: string }) {
  return http.post(`/v1/acceptance/deliverables/${deliverableId}/reject`, data)
}

/** 重新提交交付物（自由职业者） */
export function resubmitDeliverable(deliverableId: string) {
  return http.post(`/v1/acceptance/deliverables/${deliverableId}/resubmit`)
}
