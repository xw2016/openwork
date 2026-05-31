// P8 AI 验收报告页（自由职业者视角）
<script setup lang="ts">
import { useRoute } from 'vue-router'
import { NCard, NH2, NText, NEmpty, NProgress, NTag } from 'naive-ui'

const route = useRoute()
const taskId = route.params.id
</script>

<template>
  <div>
    <NH2>AI 验收报告</NH2>
    <NCard>
      <NText depth="3">合约ID: {{ taskId }}</NText>
      <div style="margin-top: 16px">
        <NEmpty description="暂无验收报告">
          <template #extra>
            <NText depth="3">提交交付物后，AI 将自动进行验收并生成报告</NText>
          </template>
        </NEmpty>
      </div>
    </NCard>
  </div>
</template>
