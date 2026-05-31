// 登录页
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import {
  NCard,
  NForm,
  NFormItem,
  NInput,
  NButton,
  NSpace,
  NText,
  NIcon,
  useMessage,
} from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { PersonOutline, LockClosedOutline } from '@vicons/ionicons5'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const message = useMessage()

const formRef = ref<FormInst | null>(null)
const formData = ref({
  email: '',
  password: '',
})

const rules: FormRules = {
  email: { required: true, message: '请输入邮箱', trigger: 'blur' },
  password: { required: true, message: '请输入密码', trigger: 'blur' },
}

async function handleLogin() {
  try {
    await formRef.value?.validate()
    await userStore.login(formData.value.email, formData.value.password)
    message.success('登录成功')
    // 根据角色跳转
    if (userStore.isEmployer) {
      router.push('/')
    } else {
      router.push('/market')
    }
  } catch (err: any) {
    if (err?.response?.data?.detail) {
      message.error(err.response.data.detail)
    }
  }
}
</script>

<template>
  <div style="height: 100vh; display: flex; align-items: center; justify-content: center; background: #f5f5f5">
    <NCard title="OpenWork 登录" style="width: 400px">
      <NForm ref="formRef" :model="formData" :rules="rules">
        <NFormItem label="邮箱" path="email">
          <NInput v-model:value="formData.email" placeholder="请输入邮箱">
            <template #prefix>
              <NIcon :component="PersonOutline" />
            </template>
          </NInput>
        </NFormItem>
        <NFormItem label="密码" path="password">
          <NInput v-model:value="formData.password" type="password" placeholder="请输入密码" show-password-on="click" @keyup.enter="handleLogin">
            <template #prefix>
              <NIcon :component="LockClosedOutline" />
            </template>
          </NInput>
        </NFormItem>
        <NSpace vertical :size="16" style="width: 100%">
          <NButton type="primary" block :loading="userStore.loading" @click="handleLogin">
            登录
          </NButton>
          <NText depth="3" style="text-align: center; display: block">
            还没有账号？
            <RouterLink to="/register">立即注册</RouterLink>
          </NText>
        </NSpace>
      </NForm>
    </NCard>
  </div>
</template>
