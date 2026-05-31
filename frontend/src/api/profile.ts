// 用户资料 API
import http from './index'

/** 用户资料 */
export interface UserProfile {
  user_id: string
  nickname: string
  avatar_url: string
  bio: string
  tags: string[]
  realname_verified: boolean
  stats: {
    completed_tasks: number
    success_rate: number
    avg_rating: number
  }
}

/** 获取用户资料 */
export function getProfile(userId: string) {
  return http.get<UserProfile>(`/v1/users/${userId}/profile`)
}

/** 更新当前用户资料 */
export function updateProfile(data: Partial<UserProfile>) {
  return http.put<UserProfile>('/v1/users/me/profile', data)
}

/** 上传头像 */
export function uploadAvatar(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return http.post<{ avatar_url: string }>('/v1/users/me/avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 实名认证 */
export function verifyRealname(data: { real_name: string; id_number: string }) {
  return http.post('/v1/users/me/verify', data)
}

/** 获取当前用户统计 */
export function getMyStats() {
  return http.get<UserProfile['stats']>('/v1/users/me/stats')
}
