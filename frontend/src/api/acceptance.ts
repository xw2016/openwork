// 验收相关 API 桩
import http from './index'
import type { AcceptanceRecord } from '@/types'

/** 触发 AI 验收 */
export function triggerAcceptance(contractId: string, deliverableId: string) {
  return http.post<AcceptanceRecord>(`/v1/contracts/${contractId}/accept`, {
    deliverable_id: deliverableId,
  })
}

/** 获取验收报告 */
export function getAcceptanceReport(contractId: string) {
  return http.get<AcceptanceRecord>(`/v1/contracts/${contractId}/acceptance`)
}

/** 确认验收结果（雇主） */
export function confirmAcceptance(contractId: string, approved: boolean) {
  return http.post(`/v1/contracts/${contractId}/confirm`, { approved })
}
