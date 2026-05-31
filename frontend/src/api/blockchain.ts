// 链上存证 API
import http from './index'

/** 存证记录 */
export interface BlockchainRecord {
  id: string
  contract_id: string
  hash: string
  node_type: string
  data: Record<string, unknown>
  verified: boolean
  created_at: string
}

/** 创建存证 */
export function createRecord(data: { contract_id: string; node_type: string; data: Record<string, unknown> }) {
  return http.post<BlockchainRecord>('/v1/blockchain/record', data)
}

/** 获取存证详情 */
export function getRecord(recordId: string) {
  return http.get<BlockchainRecord>(`/v1/blockchain/records/${recordId}`)
}

/** 验证存证 */
export function verifyRecord(recordId: string) {
  return http.post<{ verified: boolean; hash: string }>(`/v1/blockchain/records/${recordId}/verify`)
}

/** 获取合约存证列表 */
export function getContractRecords(contractId: string) {
  return http.get<BlockchainRecord[]>(`/v1/blockchain/contracts/${contractId}/records`)
}
