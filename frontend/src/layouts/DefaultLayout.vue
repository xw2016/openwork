// 默认布局：顶部导航 + 侧边栏 + 内容区
<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useRouter, useRoute, RouterView } from 'vue-router'
import {
  NLayout,
  NLayoutHeader,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NButton,
  NSpace,
  NText,
  NIcon,
  NAvatar,
  NDropdown,
} from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import {
  HomeOutline,
  CreateOutline,
  CartOutline,
  CloudUploadOutline,
  DocumentTextOutline,
  StarOutline,
  MoonOutline,
  SunnyOutline,
  LogOutOutline,
} from '@vicons/ionicons5'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import { useAuth } from '@/composables/useAuth'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const appStore = useAppStore()
const { handleLogout } = useAuth()

const collapsed = ref(false)

// 渲染图标
function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

// 根据角色生成菜单
const menuOptions = computed<MenuOption[]>(() => {
  if (userStore.isEmployer) {
    return [
      { label: '雇主首页', key: '/', icon: renderIcon(HomeOutline) },
      { label: '创建任务', key: '/employer/intent-model', icon: renderIcon(CreateOutline) },
      { label: '信用记录', key: '/credit', icon: renderIcon(StarOutline) },
    ]
  }
  if (userStore.isFreelancer) {
    return [
      { label: '任务市场', key: '/market', icon: renderIcon(CartOutline) },
      { label: '信用记录', key: '/credit', icon: renderIcon(StarOutline) },
    ]
  }
  return []
})

// 用户下拉菜单
const userDropdownOptions = [
  { label: '登出', key: 'logout', icon: renderIcon(LogOutOutline) },
]

// 菜单跳转
function handleMenuSelect(key: string) {
  router.push(key)
}

// 用户菜单操作
function handleUserDropdown(key: string) {
  if (key === 'logout') {
    handleLogout()
  }
}

// 切换暗色模式
function toggleDark() {
  appStore.toggleDarkMode()
}

// 当前激活的菜单项
const activeKey = computed(() => route.path)
</script>

<template>
  <NLayout style="height: 100vh">
    <!-- 顶部导航 -->
    <NLayoutHeader bordered style="height: 60px; padding: 0 24px; display: flex; align-items: center; justify-content: space-between">
      <NSpace align="center" :size="16">
        <NText strong style="font-size: 20px; cursor: pointer" @click="router.push('/')">
          OpenWork
        </NText>
        <NText depth="3" style="font-size: 12px">可信任务市场</NText>
      </NSpace>

      <NSpace align="center" :size="16">
        <NButton quaternary circle @click="toggleDark">
          <template #icon>
            <NIcon :component="appStore.darkMode ? SunnyOutline : MoonOutline" />
          </template>
        </NButton>

        <NDropdown :options="userDropdownOptions" @select="handleUserDropdown">
          <NSpace align="center" :size="8" style="cursor: pointer">
            <NAvatar :size="32" round>
              {{ userStore.userInfo?.username?.charAt(0)?.toUpperCase() || '?' }}
            </NAvatar>
            <NText>{{ userStore.userInfo?.username || '用户' }}</NText>
            <NText depth="3" style="font-size: 12px">
              {{ userStore.isEmployer ? '雇主' : '自由职业者' }}
            </NText>
          </NSpace>
        </NDropdown>
      </NSpace>
    </NLayoutHeader>

    <NLayout has-sider style="height: calc(100vh - 60px)">
      <!-- 侧边栏 -->
      <NLayoutSider
        bordered
        collapse-mode="width"
        :collapsed-width="64"
        :width="200"
        :collapsed="collapsed"
        show-trigger
        @collapse="collapsed = true"
        @expand="collapsed = false"
      >
        <NMenu
          :collapsed="collapsed"
          :collapsed-width="64"
          :collapsed-icon-size="22"
          :options="menuOptions"
          :value="activeKey"
          @update:value="handleMenuSelect"
        />
      </NLayoutSider>

      <!-- 内容区 -->
      <NLayoutContent style="padding: 24px; overflow-y: auto">
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>
