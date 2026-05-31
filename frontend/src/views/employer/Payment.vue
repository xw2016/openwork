<!-- P4 支付确认页 - 托管支付 + 交易记录 -->
<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NH2, NText, NButton, NSpace, NDescriptions,
  NDescriptionsItem, NAlert, NDataTable, NSpin, NResult, NTag
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { getContractDetail } from '@/api/contract'
import { createEscrow, getTransactions } from '@/api/payment'
import type { Contract, Transaction } from '@/types'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const contractId = route.params.id as string
const contract = ref<Contract | null>(null)
const transactions = ref<Transaction[]>([])
const loading = ref(true)
const paying = ref(false)
const error = ref('')
const paymentDone = ref(false)

// 平台手续费率 5%
const FEE_RATE = 0.05

const serviceFee = computed(() => {
  if (!contract.value) return 0
  return Math.round(contract.value.budget * FEE_RATE * 100) / 100
})

const totalAmount = computed(() => {
  if (!contract.value) return 0
  return Math.round((contract.value.budget + serviceFee.value) * 100) / 100
})

const transactionColumns: DataTableColumns<Transaction> = [
  { title: '交易ID', key: 'id', width: 200, ellipsis: { tooltip: true } },
  {
    title: '类型',
    key: 'type',
    width: 100,
    render(row) {
      const map: Record<string, { label: string; type: string }> = {
        payment: { label: '支付', type: 'success' },
        refund: { label: '退款', type: 'warning' },
        penalty: { label: '罚金', type: 'error' }
      }
      const info = map[row.type] || { label: row.type, type: 'default' }
      return h(NTag, { type: info.type as any, size: 'small' }, { default: () => info.label })
    }
  },
  {
    title: '金额',
    key: 'amount',
    width: 120,
    render(row) {
      return `¥${row.amount.toFixed(2)}`
    }
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render(row) {
      const map: Record<string, { label: string; type: string }> = {
        pending: { label: '处理中', type: 'warning' },
        completed: { label: '已完成', type: 'success' },
        failed: { label: '失败', type: 'error' }
      }
      const info = map[row.status] || { label: row.status, type: 'default' }
      return h(NTag, { type: info.type as any, size: 'small' }, { default: () => info.label })
    }
  },
  {
    title: '时间',
    key: 'created_at',
    width: 180,
    render(row) {
      return new Date(row.created_at).toLocaleString('zh-CN')
    }
  }
]

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await getContractDetail(contractId)
    contract.value = data
    // 加载交易记录
    try {
      const txRes = await getTransactions(contractId)
      transactions.value = txRes.data
    } catch {
      // 交易记录可能尚无，忽略错误
      transactions.value = []
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载合约信息失败'
  } finally {
    loading.value = false
  }
}

async function handlePay() {
  if (!contract.value) return
  paying.value = true
  try {
    await createEscrow({ contract_id: contractId, amount: contract.value.budget })
    message.success('托管支付成功！资金已冻结')
    paymentDone.value = true
    // 重新加载交易记录
    const txRes = await getTransactions(contractId)
    transactions.value = txRes.data
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '支付失败，请重试')
  } finally {
    paying.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="payment-page">
    <NH2>支付确认</NH2>

    <!-- 加载中 -->
    <div v-if="loading" style="display:flex;justify-content:center;padding:80px 0">
      <NSpin size="large" />
    </div>

    <!-- 错误状态 -->
    <NResult
      v-else-if="error"
      status="error"
      title="加载失败"
      :description="error"
      style="margin-top:40px"
    >
      <template #footer>
        <NButton @click="loadData">重试</NButton>
      </template>
    </NResult>

    <!-- 支付成功 -->
    <NResult
      v-else-if="paymentDone"
      status="success"
      title="支付成功"
      description="资金已冻结在托管账户中，验收通过后将自动释放给自由职业者"
      style="margin-top:40px"
    >
      <template #footer>
        <NSpace>
          <NButton type="primary" @click="router.push('/employer')">返回首页</NButton>
          <NButton @click="paymentDone = false; loadData()">查看交易记录</NButton>
        </NSpace>
      </template>
    </NResult>

    <!-- 正常内容 -->
    <template v-else-if="contract">
      <!-- 任务信息 -->
      <NCard title="任务支付信息" style="margin-bottom:16px">
        <NDescriptions bordered :column="1">
          <NDescriptionsItem label="合约ID">
            <NText code>{{ contract.id }}</NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="任务名称">{{ contract.title }}</NDescriptionsItem>
          <NDescriptionsItem label="任务预算">
            <NText strong>¥{{ contract.budget.toFixed(2) }}</NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="平台服务费（5%）">
            <NText>¥{{ serviceFee.toFixed(2) }}</NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="应付总额">
            <NText type="error" strong style="font-size:22px">¥{{ totalAmount.toFixed(2) }}</NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="合约状态">
            <NTag :type="contract.status === 'completed' ? 'success' : 'info'">
              {{ contract.status }}
            </NTag>
          </NDescriptionsItem>
        </NDescriptions>
      </NCard>

      <!-- 托管说明 -->
      <NAlert type="info" title="托管支付机制" style="margin-bottom:16px">
        资金将冻结在托管账户，验收通过后自动释放给自由职业者。如任务未完成或验收不通过，资金将退还给您。
      </NAlert>

      <!-- 操作按钮 -->
      <NSpace style="margin-bottom:24px">
        <NButton
          type="primary"
          size="large"
          :loading="paying"
          :disabled="contract.status === 'completed' || contract.status === 'cancelled'"
          @click="handlePay"
        >
          确认支付 ¥{{ totalAmount.toFixed(2) }}
        </NButton>
        <NButton size="large" @click="router.back()">返回</NButton>
      </NSpace>

      <!-- 交易记录 -->
      <NCard title="交易记录" v-if="transactions.length > 0">
        <NDataTable
          :columns="transactionColumns"
          :data="transactions"
          :bordered="false"
          size="small"
        />
      </NCard>
    </template>
  </div>
</template>

<style scoped>
.payment-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}
</style>
