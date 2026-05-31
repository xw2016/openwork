// 默认布局：顶部导航 + 侧边栏 + 内容区
<script setup lang="ts">
import { ref, computed, h, onMounted, onUnmounted } from 'vue'
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
  MenuOutline,
  CloseOutline,
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
const mobileMenuOpen = ref(false)
const isMobile = ref(false)

// Check screen size
function checkMobile() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) {
    mobileMenuOpen.value = false
  }
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

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
  if (isMobile.value) {
    mobileMenuOpen.value = false
  }
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

function toggleMobileMenu() {
  mobileMenuOpen.value = !mobileMenuOpen.value
}

// 当前激活的菜单项
const activeKey = computed(() => route.path)
</script>

<template>
  <NLayout style="height: 100vh">
    <!-- 顶部导航 -->
    <NLayoutHeader bordered style="height: 60px; padding: 0 16px; display: flex; align-items: center; justify-content: space-between">
      <NSpace align="center" :size="12">
        <!-- Mobile hamburger -->
        <NButton
          v-if="isMobile"
          quaternary
          circle
          size="small"
          @click="toggleMobileMenu"
          style="margin-right: 4px"
        >
          <template #icon>
            <NIcon :component="mobileMenuOpen ? CloseOutline : MenuOutline" />
          </template>
        </NButton>

        <NText strong style="font-size: 20px; cursor: pointer" @click="router.push('/')">
          OpenWork
        </NText>
        <NText v-if="!isMobile" depth="3" style="font-size: 12px">可信任务市场</NText>
      </NSpace>

      <NSpace align="center" :size="12">
        <NButton quaternary circle @click="toggleDark" size="small">
          <template #icon>
            <NIcon :component="appStore.darkMode ? SunnyOutline : MoonOutline" />
          </template>
        </NButton>

        <NDropdown :options="userDropdownOptions" @select="handleUserDropdown">
          <NSpace align="center" :size="6" style="cursor: pointer">
            <NAvatar :size="28" round>
              {{ userStore.userInfo?.nickname?.charAt(0)?.toUpperCase() || '?' }}
            </NAvatar>
            <NText v-if="!isMobile">{{ userStore.userInfo?.nickname || '用户' }}</NText>
          </NSpace>
        </NDropdown>
      </NSpace>
    </NLayoutHeader>

    <!-- Mobile overlay -->
    <div
      v-if="isMobile && mobileMenuOpen"
      class="mobile-sidebar-overlay"
      @click="mobileMenuOpen = false"
    />

    <NLayout has-sider style="height: calc(100vh - 60px)">
      <!-- 侧边栏 -->
      <NLayoutSider
        bordered
        collapse-mode="width"
        :collapsed-width="isMobile ? 0 : 64"
        :width="isMobile ? 220 : 200"
        :collapsed="isMobile ? !mobileMenuOpen : collapsed"
        :show-trigger="!isMobile"
        :native-scrollbar="false"
        :class="{ 'mobile-sider': isMobile, 'mobile-sider-open': isMobile && mobileMenuOpen }"
        @collapse="collapsed = true"
        @expand="collapsed = false"
      >
        <NMenu
          :collapsed="isMobile ? false : collapsed"
          :collapsed-width="64"
          :collapsed-icon-size="22"
          :options="menuOptions"
          :value="activeKey"
          @update:value="handleMenuSelect"
        />
      </NLayoutSider>

      <!-- 内容区 -->
      <NLayoutContent style="padding: 24px; overflow-y: auto" :class="{ 'mobile-content': isMobile }">
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>

<style scoped>
.mobile-sidebar-overlay {
  position: fixed;
  inset: 0;
  top: 60px;
  background: rgba(0, 0, 0, 0.4);
  z-index: 999;
}

.mobile-sider {
  position: fixed !important;
  left: 0;
  top: 60px;
  bottom: 0;
  z-index: 1000;
  transition: transform 0.3s ease;
  transform: translateX(-100%);
}

.mobile-sider-open {
  transform: translateX(0);
}

.mobile-content {
  padding: 12px !important;
}

@media (max-width: 768px) {
  .mobile-content {
    padding: 12px 8px !important;
  }
}
</style>
