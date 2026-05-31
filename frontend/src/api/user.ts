// 用户相关 API 桩
import http from './index'
import type { User, CreditRecord } from '@/types'

/** 获取用户资料 */
export function getUserProfile(userId: string) {
  return http.get<User>(`/v1/users/${userId}`)
}

/** 获取信用记录 */
export function getCreditRecords(userId: string) {
  return http.get<CreditRecord[]>(`/v1/users/${userId}/credits`)
}
