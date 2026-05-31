// P2 AI 意图建模页
<script setup lang="ts">
import { NCard, NH2, NText, NInput, NButton, NSpace, NForm, NFormItem, NInputNumber } from 'naive-ui'
</script>

<template>
  <div>
    <NH2>AI 意图建模</NH2>
    <NCard>
      <NText depth="3" style="display: block; margin-bottom: 24px">
        描述您的任务需求，AI 将自动生成结构化的任务描述和验收标准
      </NText>
      <NForm label-placement="left" label-width="80">
        <NFormItem label="任务名称">
          <NInput placeholder="例如：设计一个企业官网" />
        </NFormItem>
        <NFormItem label="需求描述">
          <NInput type="textarea" :rows="6" placeholder="请详细描述您的需求，包括功能要求、技术栈偏好、设计风格等" />
        </NFormItem>
        <NFormItem label="预算（元）">
          <NInputNumber :min="1" placeholder="请输入预算金额" style="width: 200px" />
        </NFormItem>
        <NFormItem label="截止日期">
          <NInput placeholder="YYYY-MM-DD" style="width: 200px" />
        </NFormItem>
        <NSpace>
          <NButton type="primary">AI 生成意图模型</NButton>
          <NButton>手动填写</NButton>
        </NSpace>
      </NForm>
    </NCard>
  </div>
</template>
