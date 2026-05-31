<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { useMessage, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  NCard, NH2, NText, NButton, NSpace, NStatistic, NProgress,
  NDataTable, NGrid, NGi, NDivider, NSpin, NResult, NAlert
} from 'naive-ui'
import { getMyScore, getCreditHistory, refreshCreditScore } from '@/api/credit'
import type { CreditScore, CreditHistoryItem } from '@/api/credit'
import { getContractRecords } from '@/api/blockchain'
import type { BlockchainRecord } from '@/api/blockchain'

const message = useMessage()

const scoreData = ref<CreditScore | null>(null)
const historyItems = ref<CreditHistoryItem[]>([])
const blockchainRecords = ref<BlockchainRecord[]>([])
const loading = ref(true)
const refreshing = ref(false)
const historyLoading = ref(false)
const totalRecords = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)

async function loadScore() {
  try {
    const { data } = await getMyScore()
    scoreData.value = data
  } catch {
    message.error('获取信用分失败')
  }
}

async function loadHistory(page = 1) {
  historyLoading.value = true
  try {
    const { data } = await getCreditHistory({ page, page_size: pageSize.value })
    historyItems.value = data.items
    totalRecords.value = data.total
    currentPage.value = page
  } catch {
    message.error('获取信用历史失败')
  } finally {
    historyLoading.value = false
  }
}

async function loadBlockchain() {
  try {
    // Load blockchain records for credit-related contracts
    const { data } = await getContractRecords('credit')
    blockchainRecords.value = data
  } catch {
    // Non-critical, ignore
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadScore(), loadHistory(1)])
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)

async function handleRefresh() {
  refreshing.value = true
  try {
    const { data } = await refreshCreditScore()
    scoreData.value = data
    message.success('信用分已刷新')
    await loadHistory(1)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '刷新失败，请稍后重试')
  } finally {
    refreshing.value = false
  }
}

const scoreLevel = computed(() => {
  if (!scoreData.value) return { label: '--', color: '#999' }
  const s = scoreData.value.score
  if (s >= 800) return { label: '优秀', color: '#18a058' }
  if (s >= 600) return { label: '良好', color: '#2080f0' }
  if (s >= 400) return { label: '一般', color: '#f0a020' }
  return { label: '较差', color: '#d03050' }
})

const scoreColor = computed(() => {
  if (!scoreData.value) return '#999'
  const s = scoreData.value.score
  if (s >= 800) return '#18a058'
  if (s >= 600) return '#2080f0'
  if (s >= 400) return '#f0a020'
  return '#d03050'
})

const breakdownItems = computed(() => {
  if (!scoreData.value) return []
  const b = scoreData.value.breakdown
  return [
    { label: '任务完成率', value: b.completion_rate, icon: '✓' },
    { label: '按时交付率', value: b.on_time_rate, icon: '⏱' },
    { label: '验收通过率', value: b.acceptance_rate, icon: '★' },
    { label: '争议发生率', value: b.dispute_rate, icon: '⚠', invert: true }
  ]
})

const historyColumns: DataTableColumns<CreditHistoryItem> = [
  {
    title: '时间',
    key: 'created_at',
    width: 180,
    render(row) {
      return new Date(row.created_at).toLocaleString('zh-CN')
    }
  },
  {
    title: '变动',
    key: 'change',
    width: 100,
    render(row) {
      const isPositive = row.change >= 0
      return h(NTag, {
        type: isPositive ? 'success' : 'error',
        size: 'small',
        round: true
      }, () => (isPositive ? '+' : '') + row.change)
    }
  },
  {
    title: '原因',
    key: 'reason'
  },
  {
    title: '相关合约',
    key: 'contract_id',
    width: 120,
    render(row) {
      return row.contract_id ? row.contract_id.slice(0, 8) + '...' : '--'
    }
  }
]

const pagination = computed(() => ({
  page: currentPage.value,
  pageSize: pageSize.value,
  pageCount: Math.ceil(totalRecords.value / pageSize.value),
  itemCount: totalRecords.value,
  showSizePicker: false,
  prefix: ({ itemCount }: any) => `共 ${itemCount} 条`
}))

function handlePageChange(page: number) {
  loadHistory(page)
}

function shortenHash(hash: string) {
  if (!hash || hash.length < 16) return hash
  return hash.slice(0, 8) + '...' + hash.slice(-8)
}

function formatDate(dateStr: string) {
  if (!dateStr) return '--'
  return new Date(dateStr).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="credit-page">
    <NH2>信用中心</NH2>

    <!-- Loading -->
    <NSpin v-if="loading" size="large" style="display: flex; justify-content: center; padding: 48px" />

    <template v-else>
      <!-- Score Overview -->
      <NGrid :cols="4" :x-gap="16" :y-gap="16" responsive="screen" item-responsive style="margin-bottom: 24px">
        <!-- Main Score -->
        <NGi span="4 m:2 l:1">
          <NCard style="height: 100%">
            <div style="text-align: center; padding: 16px 0">
              <NProgress
                type="circle"
                :percentage="scoreData?.score ?? 0"
                :max="1000"
                :color="scoreColor"
                :rail-color="scoreColor + '20'"
                :size="160"
                style="margin-bottom: 12px"
              >
                <template #default>
                  <div style="text-align: center">
                    <div style="font-size: 40px; font-weight: bold" :style="{ color: scoreColor }">
                      {{ scoreData?.score ?? '--' }}
                    </div>
                    <NTag :color="{ color: scoreLevel.color + '20', textColor: scoreLevel.color }" size="small" round>
                      {{ scoreLevel.label }}
                    </NTag>
                  </div>
                </template>
              </NProgress>
              <NText depth="3" style="display: block; margin-top: 8px">信用评分 (0-1000)</NText>
            </div>
          </NCard>
        </NGi>

        <!-- Breakdown Stats -->
        <NGi v-for="item in breakdownItems" :key="item.label" span="2 m:1">
          <NCard style="height: 100%">
            <NStatistic :label="item.label">
              <template #default>
                <span :style="{ color: item.invert ? (item.value > 10 ? '#d03050' : '#18a058') : (item.value >= 80 ? '#18a058' : item.value >= 60 ? '#f0a020' : '#d03050') }">
                  {{ item.value }}%
                </span>
              </template>
            </NStatistic>
          </NCard>
        </NGi>
      </NGrid>

      <!-- Refresh Button -->
      <NSpace justify="end" style="margin-bottom: 16px">
        <NButton
          type="primary"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新信用分
        </NButton>
      </NSpace>

      <!-- Credit History -->
      <NCard title="信用变动历史" style="margin-bottom: 24px">
        <NDataTable
          :columns="historyColumns"
          :data="historyItems"
          :loading="historyLoading"
          :pagination="pagination"
          :bordered="false"
          :single-line="false"
          remote
          @update:page="handlePageChange"
        />
      </NCard>

      <!-- Blockchain Attestation -->
      <NCard title="链上存证记录">
        <NAlert v-if="blockchainRecords.length === 0" type="info">
          暂无链上存证记录
        </NAlert>

        <NGrid v-else :cols="2" :x-gap="12" :y-gap="12" responsive="screen" item-responsive>
          <NGi v-for="record in blockchainRecords" :key="record.id" span="2 m:1">
            <NCard size="small" hoverable>
              <NSpace align="center" justify="space-between">
                <div>
                  <NSpace align="center" :size="8">
                    <NTag :type="record.verified ? 'success' : 'warning'" size="small">
                      {{ record.verified ? '已验证' : '待验证' }}
                    </NTag>
                    <NText strong>{{ record.node_type }}</NText>
                  </NSpace>
                  <div style="margin-top: 4px">
                    <NText depth="3" style="font-size: 12px; font-family: monospace">
                      {{ shortenHash(record.hash) }}
                    </NText>
                  </div>
                </div>
                <NText depth="3" style="font-size: 12px">
                  {{ formatDate(record.created_at) }}
                </NText>
              </NSpace>
            </NCard>
          </NGi>
        </NGrid>
      </NCard>

      <!-- Info -->
      <NAlert type="info" style="margin-top: 16px">
        信用评分基于任务完成率、按时交付率、验收通过率和争议发生率综合计算。
        评分越高，获得优质任务的机会越大。
      </NAlert>
    </template>
  </div>
</template>

<style scoped>
.credit-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 16px;
}
</style>
