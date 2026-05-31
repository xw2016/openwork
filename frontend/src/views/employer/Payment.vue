// P4 支付确认页
<script setup lang="ts">
import { useRoute } from 'vue-router'
import { NCard, NH2, NText, NButton, NSpace, NDescriptions, NDescriptionsItem } from 'naive-ui'

const route = useRoute()
const contractId = route.params.id
</script>

<template>
  <div>
    <NH2>支付确认</NH2>
    <NCard title="任务支付信息">
      <NDescriptions bordered :column="1">
        <NDescriptionsItem label="合约ID">{{ contractId }}</NDescriptionsItem>
        <NDescriptionsItem label="任务名称">--</NDescriptionsItem>
        <NDescriptionsItem label="自由职业者">--</NDescriptionsItem>
        <NDescriptionsItem label="验收结果">
          <NText type="success">待确认</NText>
        </NDescriptionsItem>
        <NDescriptionsItem label="支付金额">
          <NText type="warning" strong style="font-size: 20px">¥ --</NText>
        </NDescriptionsItem>
      </NDescriptions>

      <NSpace style="margin-top: 24px">
        <NButton type="primary" size="large">确认支付</NButton>
        <NButton size="large">取消</NButton>
      </NSpace>
    </NCard>
  </div>
</template>
