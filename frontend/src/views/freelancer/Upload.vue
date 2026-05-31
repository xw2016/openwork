// P7 交付物上传页
<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { NCard, NH2, NText, NButton, NSpace, NUpload, NInput, NFormItem, NForm } from 'naive-ui'

const route = useRoute()
const router = useRouter()
const taskId = route.params.id
</script>

<template>
  <div>
    <NH2>提交交付物</NH2>
    <NCard>
      <NText depth="3" style="display: block; margin-bottom: 16px">合约ID: {{ taskId }}</NText>
      <NForm label-placement="left" label-width="100">
        <NFormItem label="交付物文件">
          <NUpload action="#" :max="5" style="width: 100%">
            <NButton>选择文件上传</NButton>
          </NUpload>
        </NFormItem>
        <NFormItem label="说明">
          <NInput type="textarea" :rows="4" placeholder="请描述交付物内容和注意事项" />
        </NFormItem>
        <NSpace>
          <NButton type="primary">提交交付物</NButton>
          <NButton @click="router.back()">返回</NButton>
        </NSpace>
      </NForm>
    </NCard>
  </div>
</template>
