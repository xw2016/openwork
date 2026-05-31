// 注册页
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
  NRadioGroup,
  NRadioButton,
  useMessage,
} from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { useUserStore } from '@/stores/user'
import type { UserRole } from '@/types'

const router = useRouter()
const userStore = useUserStore()
const message = useMessage()

const formRef = ref<FormInst | null>(null)
const formData = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  role: 'freelancer' as UserRole,
})

const rules: FormRules = {
  username: { required: true, message: '请输入用户名', trigger: 'blur' },
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirmPassword: {
    required: true,
    trigger: 'blur',
    validator: (_rule: any, value: string) => {
      if (value !== formData.value.password) {
        return new Error('两次密码不一致')
      }
      return true
    },
  },
}

async function handleRegister() {
  try {
    await formRef.value?.validate()
    await userStore.register(
      formData.value.username,
      formData.value.email,
      formData.value.password,
      formData.value.role
    )
    message.success('注册成功，请登录')
    router.push('/login')
  } catch (err: any) {
    if (err?.response?.data?.detail) {
      message.error(err.response.data.detail)
    }
  }
}
</script>

<template>
  <div style="height: 100vh; display: flex; align-items: center; justify-content: center; background: #f5f5f5">
    <NCard title="OpenWork 注册" style="width: 450px">
      <NForm ref="formRef" :model="formData" :rules="rules">
        <NFormItem label="角色" path="role">
          <NRadioGroup v-model:value="formData.role">
            <NRadioButton value="employer">雇主</NRadioButton>
            <NRadioButton value="freelancer">自由职业者</NRadioButton>
          </NRadioGroup>
        </NFormItem>
        <NFormItem label="用户名" path="username">
          <NInput v-model:value="formData.username" placeholder="请输入用户名" />
        </NFormItem>
        <NFormItem label="邮箱" path="email">
          <NInput v-model:value="formData.email" placeholder="请输入邮箱" />
        </NFormItem>
        <NFormItem label="密码" path="password">
          <NInput v-model:value="formData.password" type="password" placeholder="请输入密码（至少6位）" show-password-on="click" />
        </NFormItem>
        <NFormItem label="确认密码" path="confirmPassword">
          <NInput v-model:value="formData.confirmPassword" type="password" placeholder="请再次输入密码" show-password-on="click" @keyup.enter="handleRegister" />
        </NFormItem>
        <NSpace vertical :size="16" style="width: 100%">
          <NButton type="primary" block :loading="userStore.loading" @click="handleRegister">
            注册
          </NButton>
          <NText depth="3" style="text-align: center; display: block">
            已有账号？
            <RouterLink to="/login">去登录</RouterLink>
          </NText>
        </NSpace>
      </NForm>
    </NCard>
  </div>
</template>
