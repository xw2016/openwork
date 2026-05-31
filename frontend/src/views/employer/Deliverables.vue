// P3 交付物与验收确认页
<script setup lang="ts">
import { useRoute } from 'vue-router'
import { NCard, NH2, NText, NButton, NSpace, NTag, NEmpty } from 'naive-ui'

const route = useRoute()
const contractId = route.params.id
</script>

<template>
  <div>
    <NH2>交付物与验收确认</NH2>
    <NCard>
      <NText depth="3">合约ID: {{ contractId }}</NText>
      <div style="margin-top: 16px">
        <NEmpty description="暂无交付物">
          <template #extra>
            <NText depth="3">等待自由职业者提交交付物后，AI 将自动进行验收</NText>
          </template>
        </NEmpty>
      </div>
    </NCard>

    <NCard title="AI 验收报告" style="margin-top: 16px">
      <NEmpty description="暂无验收报告" />
    </NCard>

    <NSpace style="margin-top: 16px">
      <NButton type="primary" disabled>确认验收通过</NButton>
      <NButton type="error" disabled>拒绝验收</NButton>
    </NSpace>
  </div>
</template>
