// 认证相关 API
import http from './index'
import type { LoginRequest, RegisterRequest, LoginResponse, User } from '@/types'

/** 用户注册 */
export function register(data: RegisterRequest) {
  return http.post<User>('/v1/auth/register', data)
}

/** 用户登录 */
export function login(data: LoginRequest) {
  return http.post<LoginResponse>('/v1/auth/login', data)
}

/** 获取当前用户信息 */
export function getMe() {
  return http.get<User>('/v1/auth/me')
}
