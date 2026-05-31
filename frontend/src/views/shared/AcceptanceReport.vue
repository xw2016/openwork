<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NH2, NText, NButton, NSpace, NProgress, NTag,
  NDescriptions, NDescriptionsItem, NAlert, NModal, NInput,
  NSpin, NResult, NCollapse, NCollapseItem, NList, NListItem,
  NDivider, NEmpty
} from 'naive-ui'
import type { AcceptanceRecord } from '@/types'
import { getAcceptanceRecords, getAcceptanceDetail, rejectDeliverable } from '@/api/acceptance'
import { releaseEscrow } from '@/api/payment'
import { getContractDetail } from '@/api/contract'
import { getContractRecords } from '@/api/blockchain'
import type { BlockchainRecord } from '@/api/blockchain'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const contractId = route.params.id as string

const records = ref<AcceptanceRecord[]>([])
const selectedRecord = ref<AcceptanceRecord | null>(null)
const blockchainRecords = ref<BlockchainRecord[]>([])
const loading = ref(true)
const detailLoading = ref(false)
const actionLoading = ref(false)
const contractTitle = ref('')
const contractStatus = ref('')
const budget = ref(0)

// Reject dialog
const showRejectModal = ref(false)
const rejectReason = ref('')
const rejectDeliverableId = ref('')

async function loadData() {
  loading.value = true
  try {
    const [recordsRes, contractRes, blockchainRes] = await Promise.all([
      getAcceptanceRecords(contractId),
      getContractDetail(contractId),
      getContractRecords(contractId).catch(() => ({ data: [] }))
    ])
    records.value = recordsRes.data
    contractTitle.value = contractRes.data.title
    contractStatus.value = contractRes.data.status
    budget.value = contractRes.data.budget
    blockchainRecords.value = blockchainRes.data

    if (records.value.length > 0) {
      await loadDetail(records.value[0].id)
    }
  } catch {
    message.error('加载验收数据失败')
  } finally {
    loading.value = false
  }
}

async function loadDetail(recordId: string) {
  detailLoading.value = true
  try {
    const { data } = await getAcceptanceDetail(recordId)
    selectedRecord.value = data
  } catch {
    message.error('加载验收详情失败')
  } finally {
    detailLoading.value = false
  }
}

onMounted(loadData)

const scoreColor = computed(() => {
  if (!selectedRecord.value) return '#999'
  const s = selectedRecord.value.score
  if (s >= 80) return '#18a058'
  if (s >= 60) return '#f0a020'
  return '#d03050'
})

async function handleApprove() {
  if (!selectedRecord.value) return
  actionLoading.value = true
  try {
    await releaseEscrow(contractId)
    message.success('验收已确认通过，资金已释放给自由职业者')
    contractStatus.value = 'completed'
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '确认失败，请重试')
  } finally {
    actionLoading.value = false
  }
}

function openRejectDialog() {
  rejectReason.value = ''
  if (selectedRecord.value) {
    rejectDeliverableId.value = selectedRecord.value.deliverable_id
  }
  showRejectModal.value = true
}

async function handleReject() {
  if (!rejectReason.value.trim()) {
    message.warning('请填写驳回原因')
    return
  }
  actionLoading.value = true
  try {
    await rejectDeliverable(rejectDeliverableId.value, { reason: rejectReason.value })
    message.success('已驳回交付物，自由职业者将收到通知')
    showRejectModal.value = false
    contractStatus.value = 'disputed'
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '驳回失败，请重试')
  } finally {
    actionLoading.value = false
  }
}

function formatDate(dateStr: string) {
  if (!dateStr) return '--'
  return new Date(dateStr).toLocaleString('zh-CN')
}

function shortenHash(hash: string) {
  if (!hash || hash.length < 16) return hash
  return hash.slice(0, 8) + '...' + hash.slice(-8)
}
</script>

<template>
  <div class="report-page">
    <NH2>
      验收报告
      <NText v-if="contractTitle" depth="3" style="font-size: 14px; margin-left: 8px">
        {{ contractTitle }}
      </NText>
    </NH2>

    <!-- Loading -->
    <NSpin v-if="loading" size="large" style="display: flex; justify-content: center; padding: 48px" />

    <!-- No records -->
    <NResult
      v-else-if="records.length === 0"
      status="info"
      title="暂无验收报告"
      description="自由职业者尚未提交交付物，或 AI 验收尚未完成"
    >
      <template #footer>
        <NButton @click="router.back()">返回</NButton>
      </template>
    </NResult>

    <template v-else>
      <!-- Contract Info -->
      <NCard title="合约信息" style="margin-bottom: 16px">
        <NDescriptions bordered :column="2">
          <NDescriptionsItem label="合约ID">{{ contractId }}</NDescriptionsItem>
          <NDescriptionsItem label="合约状态">
            <NTag :type="contractStatus === 'completed' ? 'success' : contractStatus === 'disputed' ? 'error' : 'info'">
              {{ contractStatus }}
            </NTag>
          </NDescriptionsItem>
          <NDescriptionsItem label="预算金额">
            <NText strong type="warning" style="font-size: 18px">¥ {{ budget }}</NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="验收时间">
            {{ formatDate(selectedRecord?.created_at || '') }}
          </NDescriptionsItem>
        </NDescriptions>
      </NCard>

      <!-- Score Card -->
      <NCard style="margin-bottom: 16px">
        <div style="text-align: center; padding: 24px 0">
          <NProgress
            type="circle"
            :percentage="selectedRecord?.score ?? 0"
            :color="scoreColor"
            :rail-color="scoreColor + '20'"
            :size="180"
            style="margin-bottom: 20px"
          >
            <template #default>
              <div style="text-align: center">
                <div style="font-size: 42px; font-weight: bold" :style="{ color: scoreColor }">
                  {{ selectedRecord?.score ?? '--' }}
                </div>
                <div style="font-size: 14px; color: #999">综合评分</div>
              </div>
            </template>
          </NProgress>

          <NTag
            :type="selectedRecord?.passed ? 'success' : 'error'"
            size="large"
            round
          >
            {{ selectedRecord?.passed ? 'AI 验收通过' : 'AI 验收未通过' }}
          </NTag>

          <NText v-if="selectedRecord?.report" depth="3" style="display: block; margin-top: 16px; font-size: 14px; max-width: 600px; margin-left: auto; margin-right: auto">
            {{ selectedRecord.report }}
          </NText>
        </div>
      </NCard>

      <!-- Criteria Breakdown -->
      <NCollapse v-if="selectedRecord?.details && selectedRecord.details.length > 0" default-expanded-names="criteria">
        <NCollapseItem title="验收标准详情" name="criteria">
          <NCard>
            <NList bordered>
              <NListItem v-for="(detail, idx) in selectedRecord.details" :key="idx">
                <NSpace align="center" justify="space-between" style="width: 100%">
                  <div style="flex: 1">
                    <NSpace align="center" :size="8">
                      <NTag :type="detail.passed ? 'success' : 'error'" size="small">
                        {{ detail.passed ? '✓ 通过' : '✗ 未通过' }}
                      </NTag>
                      <NText strong>{{ detail.criterion }}</NText>
                    </NSpace>
                    <div v-if="detail.comment" style="margin-top: 6px">
                      <NText depth="3" style="font-size: 13px">{{ detail.comment }}</NText>
                    </div>
                  </div>
                  <div style="min-width: 60px; text-align: right">
                    <NText strong :style="{ color: detail.score >= 60 ? '#18a058' : '#d03050', fontSize: '18px' }">
                      {{ detail.score }}
                    </NText>
                    <NText depth="3" style="font-size: 12px"> 分</NText>
                  </div>
                </NSpace>
              </NListItem>
            </NList>
          </NCard>
        </NCollapseItem>
      </NCollapse>

      <!-- Blockchain Attestation -->
      <NCard v-if="blockchainRecords.length > 0" title="链上存证" style="margin-top: 16px">
        <NList bordered>
          <NListItem v-for="record in blockchainRecords" :key="record.id">
            <NSpace align="center" justify="space-between" style="width: 100%">
              <div>
                <NSpace align="center" :size="8">
                  <NTag :type="record.verified ? 'success' : 'warning'" size="small">
                    {{ record.verified ? '已验证' : '待验证' }}
                  </NTag>
                  <NText strong>{{ record.node_type }}</NText>
                </NSpace>
                <div style="margin-top: 4px">
                  <NText depth="3" style="font-size: 12px; font-family: monospace">
                    哈希: {{ shortenHash(record.hash) }}
                  </NText>
                </div>
              </div>
              <NText depth="3" style="font-size: 12px">
                {{ formatDate(record.created_at) }}
              </NText>
            </NSpace>
          </NListItem>
        </NList>
      </NCard>

      <NAlert v-else type="info" style="margin-top: 16px">
        暂无链上存证记录
      </NAlert>

      <!-- Action Buttons -->
      <NCard title="操作" style="margin-top: 24px">
        <NAlert
          v-if="contractStatus === 'completed'"
          type="success"
          style="margin-bottom: 16px"
        >
          该合约已完成，资金已释放。
        </NAlert>
        <NAlert
          v-else-if="contractStatus === 'disputed'"
          type="error"
          style="margin-bottom: 16px"
        >
          该合约已进入争议状态。
        </NAlert>

        <NSpace v-if="contractStatus !== 'completed' && contractStatus !== 'disputed'">
          <NButton
            type="primary"
            size="large"
            :loading="actionLoading"
            @click="handleApprove"
          >
            确认通过并释放资金
          </NButton>
          <NButton
            type="error"
            size="large"
            :loading="actionLoading"
            @click="openRejectDialog"
          >
            驳回交付物
          </NButton>
        </NSpace>

        <NSpace>
          <NButton @click="router.back()">返回</NButton>
        </NSpace>
      </NCard>

      <!-- Reject Modal -->
      <NModal
        v-model:show="showRejectModal"
        preset="dialog"
        title="驳回交付物"
        positive-text="确认驳回"
        negative-text="取消"
        :loading="actionLoading"
        @positive-click="handleReject"
      >
        <div style="margin-bottom: 16px">
          <NText>请说明驳回原因，自由职业者将收到通知并可以重新提交：</NText>
        </div>
        <NInput
          v-model:value="rejectReason"
          type="textarea"
          :rows="4"
          placeholder="请输入驳回原因..."
        />
      </NModal>
    </template>
  </div>
</template>

<style scoped>
.report-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px;
}
</style>
