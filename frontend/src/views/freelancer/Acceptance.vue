<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NH2, NText, NButton, NSpace, NProgress, NTag,
  NList, NListItem, NAlert, NTimeline, NTimelineItem,
  NSpin, NResult, NEmpty, NDivider, NCollapse, NCollapseItem
} from 'naive-ui'
import type { AcceptanceRecord } from '@/types'
import { getAcceptanceRecords, getAcceptanceDetail, resubmitDeliverable } from '@/api/acceptance'
import { getContractDetail } from '@/api/contract'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const taskId = route.params.id as string

const records = ref<AcceptanceRecord[]>([])
const selectedRecord = ref<AcceptanceRecord | null>(null)
const loading = ref(true)
const detailLoading = ref(false)
const resubmitting = ref(false)
const contractTitle = ref('')
const contractStatus = ref('')

async function loadData() {
  loading.value = true
  try {
    const [recordsRes, contractRes] = await Promise.all([
      getAcceptanceRecords(taskId),
      getContractDetail(taskId)
    ])
    records.value = recordsRes.data
    contractTitle.value = contractRes.data.title
    contractStatus.value = contractRes.data.status

    // Auto-select the latest record
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

const scoreStatus = computed(() => {
  if (!selectedRecord.value) return 'default'
  return selectedRecord.value.passed ? 'success' : 'error'
})

async function handleResubmit() {
  if (!selectedRecord.value) return
  resubmitting.value = true
  try {
    await resubmitDeliverable(selectedRecord.value.deliverable_id)
    message.success('重新提交成功，请重新上传交付物')
    router.push(`/task/${taskId}/upload`)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '重新提交失败')
  } finally {
    resubmitting.value = false
  }
}

function formatDate(dateStr: string) {
  if (!dateStr) return '--'
  return new Date(dateStr).toLocaleString('zh-CN')
}

function getRecordStatusType(record: AcceptanceRecord) {
  return record.passed ? 'success' : 'error'
}

function getRecordStatusLabel(record: AcceptanceRecord) {
  return record.passed ? '通过' : '未通过'
}
</script>

<template>
  <div class="acceptance-page">
    <NH2>
      AI 验收报告
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
      title="暂无验收记录"
      description="提交交付物后，AI 将自动进行验收评估"
    >
      <template #footer>
        <NButton type="primary" @click="router.push(`/task/${taskId}/upload`)">
          去提交交付物
        </NButton>
      </template>
    </NResult>

    <template v-else>
      <!-- Main Result Card -->
      <NCard style="margin-bottom: 24px">
        <div style="text-align: center; padding: 16px 0">
          <NProgress
            type="circle"
            :percentage="selectedRecord?.score ?? 0"
            :color="scoreColor"
            :rail-color="scoreColor + '20'"
            :size="160"
            style="margin-bottom: 16px"
          >
            <template #default>
              <div style="text-align: center">
                <div style="font-size: 36px; font-weight: bold" :style="{ color: scoreColor }">
                  {{ selectedRecord?.score ?? '--' }}
                </div>
                <div style="font-size: 14px; color: #999">综合评分</div>
              </div>
            </template>
          </NProgress>

          <div>
            <NTag :type="scoreStatus as any" size="large" round>
              {{ selectedRecord?.passed ? '验收通过' : '验收未通过' }}
            </NTag>
          </div>

          <NText v-if="selectedRecord?.report" depth="3" style="display: block; margin-top: 12px; font-size: 14px">
            {{ selectedRecord.report }}
          </NText>
        </div>
      </NCard>

      <!-- Detail Breakdown -->
      <NCollapse v-if="selectedRecord?.details && selectedRecord.details.length > 0" default-expanded-names="details">
        <NCollapseItem title="验收详情" name="details">
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
                    <div v-if="detail.comment" style="margin-top: 8px">
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

      <!-- Failed Actions -->
      <NAlert
        v-if="selectedRecord && !selectedRecord.passed"
        type="warning"
        style="margin-top: 16px"
      >
        <template #header>
          <NText strong>验收未通过</NText>
        </template>
        请根据验收反馈修改交付物后重新提交。点击下方按钮前往重新上传。
        <template #footer>
          <NButton
            type="warning"
            :loading="resubmitting"
            @click="handleResubmit"
            style="margin-top: 8px"
          >
            重新提交交付物
          </NButton>
        </template>
      </NAlert>

      <!-- Passed Info -->
      <NAlert
        v-if="selectedRecord?.passed"
        type="success"
        style="margin-top: 16px"
      >
        <template #header>
          <NText strong>验收通过</NText>
        </template>
        恭喜！你的交付物已通过 AI 验收，等待雇主确认后将释放托管资金。
      </NAlert>

      <!-- Acceptance History Timeline -->
      <NCard title="验收历史" style="margin-top: 24px">
        <NTimeline v-if="records.length > 0">
          <NTimelineItem
            v-for="record in records"
            :key="record.id"
            :type="getRecordStatusType(record) as any"
            :title="`验收评分: ${record.score} 分`"
            :content="`状态: ${getRecordStatusLabel(record)} | ${formatDate(record.created_at)}`"
            :time="formatDate(record.created_at)"
            @click="loadDetail(record.id)"
            style="cursor: pointer"
          />
        </NTimeline>
        <NEmpty v-else description="暂无验收历史" />
      </NCard>

      <!-- Navigation -->
      <NSpace style="margin-top: 24px">
        <NButton @click="router.push(`/task/${taskId}/upload`)">
          查看交付物
        </NButton>
        <NButton @click="router.back()">
          返回
        </NButton>
      </NSpace>
    </template>
  </div>
</template>

<style scoped>
.acceptance-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px;
}
</style>
