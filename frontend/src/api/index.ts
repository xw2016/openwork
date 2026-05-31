// Axios 实例封装，含 JWT 拦截器
import axios from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios'

// 创建 Axios 实例，baseURL 为空（走 Vite 代理）
const http: AxiosInstance = axios.create({
  baseURL: '',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：自动添加 JWT Token
http.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：解包 {code, message, data} + 处理 401
http.interceptors.response.use(
  (response: AxiosResponse) => {
    // 后端统一返回 {code, message, data}，自动解包
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body && 'data' in body) {
      response.data = body.data
      // 保留原始 code 和 message 以备需要
      ;(response as any)._raw = body
    }
    return response
  },
  (error) => {
    if (error.response?.status === 401) {
      // 清除本地 token 并跳转登录页
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default http
