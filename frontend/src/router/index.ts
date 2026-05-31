// 路由配置
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/auth/Register.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      // P1-P4 雇主页面
      {
        path: '',
        name: 'EmployerHome',
        component: () => import('@/views/employer/Home.vue'),
        meta: { role: 'employer' },
      },
      {
        path: 'employer/intent-model/:id?',
        name: 'IntentModel',
        component: () => import('@/views/employer/IntentModel.vue'),
        meta: { role: 'employer' },
      },
      {
        path: 'employer/deliverables/:id',
        name: 'Deliverables',
        component: () => import('@/views/employer/Deliverables.vue'),
        meta: { role: 'employer' },
      },
      {
        path: 'employer/payment/:id',
        name: 'Payment',
        component: () => import('@/views/employer/Payment.vue'),
        meta: { role: 'employer' },
      },
      // P5-P8 自由职业者页面
      {
        path: 'market',
        name: 'Market',
        component: () => import('@/views/freelancer/Market.vue'),
        meta: { role: 'freelancer' },
      },
      {
        path: 'task/:id',
        name: 'TaskDetail',
        component: () => import('@/views/freelancer/TaskDetail.vue'),
        meta: { role: 'freelancer' },
      },
      {
        path: 'task/:id/upload',
        name: 'Upload',
        component: () => import('@/views/freelancer/Upload.vue'),
        meta: { role: 'freelancer' },
      },
      {
        path: 'task/:id/acceptance',
        name: 'Acceptance',
        component: () => import('@/views/freelancer/Acceptance.vue'),
        meta: { role: 'freelancer' },
      },
      // P9-P10 共享页面
      {
        path: 'contract/:id/report',
        name: 'AcceptanceReport',
        component: () => import('@/views/shared/AcceptanceReport.vue'),
      },
      {
        path: 'credit',
        name: 'Credit',
        component: () => import('@/views/shared/Credit.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()

  // 不需要认证的页面直接放行
  if (to.meta.requiresAuth === false) {
    // 已登录用户访问登录/注册页时跳转首页
    if (userStore.isLoggedIn) {
      return next('/')
    }
    return next()
  }

  // 未登录则跳转登录页
  if (!userStore.isLoggedIn) {
    return next('/login')
  }

  // 已登录但未获取用户信息时，先获取
  if (!userStore.userInfo) {
    try {
      await userStore.fetchUser()
    } catch {
      return next('/login')
    }
  }

  // 角色权限检查
  const requiredRole = to.meta.role as string | undefined
  if (requiredRole && userStore.userRole !== requiredRole) {
    // 角色不匹配，跳转到对应角色的首页
    if (userStore.isEmployer) return next('/')
    if (userStore.isFreelancer) return next('/market')
    return next('/login')
  }

  next()
})

export default router
