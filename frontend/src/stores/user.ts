// 用户状态管理
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, UserRole } from '@/types'
import { login as loginApi, register as registerApi, getMe } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  // 状态
  const token = ref<string>(localStorage.getItem('token') || '')
  const userInfo = ref<User | null>(null)
  const loading = ref(false)

  // 计算属性
  const isLoggedIn = computed(() => !!token.value)
  const userRole = computed(() => userInfo.value?.user_type || null)
  const isEmployer = computed(() => userRole.value === 'employer')
  const isFreelancer = computed(() => userRole.value === 'freelancer')

  // 登录
  async function login(email: string, password: string) {
    loading.value = true
    try {
      const { data: res } = await loginApi({ email, password })
      // 后端返回 {code, message, data: {access_token, refresh_token, ...}}
      const tokenData = res.data ?? res
      token.value = tokenData.access_token
      localStorage.setItem('token', tokenData.access_token)
      // 登录成功后获取用户信息
      await fetchUser()
    } finally {
      loading.value = false
    }
  }

  // 注册
  async function register(nickname: string, email: string, password: string, user_type: UserRole) {
    loading.value = true
    try {
      await registerApi({ nickname, email, password, user_type })
    } finally {
      loading.value = false
    }
  }

  // 获取当前用户信息
  async function fetchUser() {
    if (!token.value) return
    try {
      const { data: res } = await getMe()
      // 后端返回 {code, message, data}，实际用户在 res.data 里
      userInfo.value = res.data ?? res
    } catch {
      // token 无效则清除
      logout()
    }
  }

  // 登出
  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
  }

  return {
    token,
    userInfo,
    loading,
    isLoggedIn,
    userRole,
    isEmployer,
    isFreelancer,
    login,
    register,
    fetchUser,
    logout,
  }
})
