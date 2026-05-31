// P10 信用记录页
<script setup lang="ts">
import { NCard, NH2, NText, NEmpty, NDataTable, NStatistic, NGrid, NGi } from 'naive-ui'

// 表格列定义
const columns = [
  { title: '时间', key: 'created_at', width: 180 },
  { title: '变动', key: 'change', width: 100 },
  { title: '原因', key: 'reason' },
  { title: '相关合约', key: 'contract_id', width: 120 },
]

const data: any[] = []
</script>

<template>
  <div>
    <NH2>信用记录</NH2>
    <NGrid :cols="3" :x-gap="16" style="margin-bottom: 24px">
      <NGi>
        <NCard>
          <NStatistic label="当前信用分" :value="100" />
        </NCard>
      </NGi>
      <NGi>
        <NCard>
          <NStatistic label="完成任务数" :value="0" />
        </NCard>
      </NGi>
      <NGi>
        <NCard>
          <NStatistic label="好评率" :value="0" suffix="%" />
        </NCard>
      </NGi>
    </NGrid>

    <NCard title="信用变动历史">
      <NDataTable :columns="columns" :data="data" :bordered="false" />
    </NCard>
  </div>
</template>
