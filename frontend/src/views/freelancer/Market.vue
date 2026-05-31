// P5 任务市场页
<script setup lang="ts">
import { NCard, NH2, NText, NButton, NSpace, NTag, NGrid, NGi, NEmpty } from 'naive-ui'
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div>
    <NSpace justify="space-between" align="center">
      <NH2>任务市场</NH2>
      <NText depth="3">浏览可用的任务并接单</NText>
    </NSpace>

    <NEmpty description="暂无可用任务" style="margin-top: 60px">
      <template #extra>
        <NText depth="3">雇主发布任务后将在此显示</NText>
      </template>
    </NEmpty>
  </div>
</template>
