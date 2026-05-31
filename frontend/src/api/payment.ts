// 资金结算 API
import http from './index'
import type { Transaction } from '@/types'

/** 创建托管冻结 */
export function createEscrow(data: { contract_id: string; amount: number }) {
  return http.post<Transaction>('/v1/payment/escrow', data)
}

/** 释放托管资金 */
export function releaseEscrow(contractId: string) {
  return http.post(`/v1/payment/contracts/${contractId}/release`)
}

/** 退款 */
export function refundEscrow(contractId: string) {
  return http.post(`/v1/payment/contracts/${contractId}/refund`)
}

/** 获取合约交易记录 */
export function getTransactions(contractId: string) {
  return http.get<Transaction[]>(`/v1/payment/contracts/${contractId}/transactions`)
}
