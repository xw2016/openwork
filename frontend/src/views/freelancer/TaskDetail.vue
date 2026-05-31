// P6 任务详情页
<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { NCard, NH2, NText, NButton, NSpace, NTag, NDescriptions, NDescriptionsItem } from 'naive-ui'

const route = useRoute()
const router = useRouter()
const taskId = route.params.id
</script>

<template>
  <div>
    <NH2>任务详情</NH2>
    <NCard>
      <NDescriptions bordered :column="2">
        <NDescriptionsItem label="任务ID">{{ taskId }}</NDescriptionsItem>
        <NDescriptionsItem label="状态">
          <NTag type="info">待接单</NTag>
        </NDescriptionsItem>
        <NDescriptionsItem label="任务名称">--</NDescriptionsItem>
        <NDescriptionsItem label="预算">¥ --</NDescriptionsItem>
        <NDescriptionsItem label="描述" :span="2">--</NDescriptionsItem>
        <NDescriptionsItem label="验收标准" :span="2">--</NDescriptionsItem>
      </NDescriptions>

      <NSpace style="margin-top: 24px">
        <NButton type="primary" @click="router.push(`/task/${taskId}/upload`)">接单并提交交付物</NButton>
        <NButton @click="router.back()">返回</NButton>
      </NSpace>
    </NCard>
  </div>
</template>
