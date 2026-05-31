// 认证相关组合式函数
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { computed } from 'vue'

export function useAuth() {
  const router = useRouter()
  const userStore = useUserStore()

  const isLoggedIn = computed(() => userStore.isLoggedIn)
  const userInfo = computed(() => userStore.userInfo)
  const userRole = computed(() => userStore.userRole)

  async function handleLogin(username: string, password: string) {
    await userStore.login(username, password)
    await router.push('/')
  }

  async function handleRegister(username: string, email: string, password: string, role: 'employer' | 'freelancer') {
    await userStore.register(username, email, password, role)
    await router.push('/login')
  }

  async function handleLogout() {
    userStore.logout()
    await router.push('/login')
  }

  return {
    isLoggedIn,
    userInfo,
    userRole,
    handleLogin,
    handleRegister,
    handleLogout,
  }
}
