// P1 雇主首页
<script setup lang="ts">
import { NCard, NH2, NText, NButton, NSpace, NGrid, NGi } from 'naive-ui'
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div>
    <NH2>雇主首页</NH2>
    <NGrid :cols="3" :x-gap="16" :y-gap="16">
      <NGi>
        <NCard title="创建新任务">
          <NText depth="3">通过 AI 意图建模，快速创建精准任务描述</NText>
          <template #footer>
            <NButton type="primary" @click="router.push('/employer/intent-model')">
              开始创建
            </NButton>
          </template>
        </NCard>
      </NGi>
      <NGi>
        <NCard title="进行中的任务">
          <NText depth="3">查看当前正在进行的任务状态</NText>
          <template #footer>
            <NText>暂无进行中的任务</NText>
          </template>
        </NCard>
      </NGi>
      <NGi>
        <NCard title="待验收的交付物">
          <NText depth="3">查看 AI 验收报告并确认</NText>
          <template #footer>
            <NText>暂无待验收的交付物</NText>
          </template>
        </NCard>
      </NGi>
    </NGrid>
  </div>
</template>
