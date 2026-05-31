// P9 AI 验收报告页（雇主视角）
<script setup lang="ts">
import { useRoute } from 'vue-router'
import { NCard, NH2, NText, NEmpty, NButton, NSpace } from 'naive-ui'

const route = useRoute()
const contractId = route.params.id
</script>

<template>
  <div>
    <NH2>验收报告（雇主视角）</NH2>
    <NCard>
      <NText depth="3">合约ID: {{ contractId }}</NText>
      <div style="margin-top: 16px">
        <NEmpty description="暂无验收报告" />
      </div>
      <NSpace style="margin-top: 24px">
        <NButton type="primary" disabled>确认通过</NButton>
        <NButton type="error" disabled>拒绝</NButton>
      </NSpace>
    </NCard>
  </div>
</template>
