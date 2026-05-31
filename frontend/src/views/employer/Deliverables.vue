// P3 交付物与验收确认页
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard,
  NButton,
  NSpace,
  NTag,
  NEmpty,
  NDescriptions,
  NDescriptionsItem,
  NSpin,
  NList,
  NListItem,
  NIcon,
  NText,
  NPopconfirm,
  NAlert,
  NBreadcrumb,
  NBreadcrumbItem,
  NGrid,
  NGi,
  NStatistic,
  NResult,
} from 'naive-ui'
import {
  DocumentTextOutline,
  CloudDownloadOutline,
  TimeOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline,
  ArrowBackOutline,
  SendOutline,
} from '@vicons/ionicons5'
import { getContractDetail, getDeliverables, publishContract, terminateContract } from '@/api/contract'
import type { Contract, Deliverable, ContractStatus } from '@/types'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const contractId = computed(() => route.params.id as string)

// ---------- 状态 ----------
const loading = ref(true)
const deliverablesLoading = ref(false)
const publishLoading = ref(false)
const terminateLoading = ref(false)

const contract = ref<Contract | null>(null)
const deliverables = ref<Deliverable[]>([])
const error = ref<string | null>(null)

// ---------- 状态映射 ----------
const statusMap: Record<ContractStatus, { label: string; type: 'success' | 'warning' | 'info' | 'error' | 'default' }> = {
  draft: { label: '草稿', type: 'default' },
  pending_accept: { label: '待接单', type: 'warning' },
  in_progress: { label: '进行中', type: 'info' },
  submitted: { label: '已提交交付物', type: 'warning' },
  reviewing: { label: 'AI验收中', type: 'info' },
  completed: { label: '已完成', type: 'success' },
  disputed: { label: '争议中', type: 'error' },
  cancelled: { label: '已取消', type: 'default' },
}

// ---------- 计算属性 ----------
const contractStatus = computed(() => {
  if (!contract.value) return null
  return statusMap[contract.value.status] || { label: contract.value.status, type: 'default' as const }
})

const canPublish = computed(() => contract.value?.status === 'draft')
const canSubmitAcceptance = computed(() => {
  return (
    deliverables.value.length > 0 &&
    contract.value &&
    ['in_progress', 'submitted'].includes(contract.value.status)
  )
})
const canTerminate = computed(() => {
  return (
    contract.value &&
    !['completed', 'cancelled'].includes(contract.value.status)
  )
})

// ---------- 格式化 ----------
function formatDate(dateStr: string): string {
  if (!dateStr) return '--'
  try {
    const d = new Date(dateStr)
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

// ---------- API 调用 ----------
async function fetchContractDetail() {
  loading.value = true
  error.value = null
  try {
    const { data } = await getContractDetail(contractId.value)
    contract.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载合约信息失败'
    message.error(error.value!)
  } finally {
    loading.value = false
  }
}

async function fetchDeliverables() {
  deliverablesLoading.value = true
  try {
    const { data } = await getDeliverables(contractId.value)
    deliverables.value = Array.isArray(data) ? data : []
  } catch (err: any) {
    // 交付物为空时不报错
    if (err?.response?.status !== 404) {
      message.error(err?.response?.data?.detail || '加载交付物失败')
    }
    deliverables.value = []
  } finally {
    deliverablesLoading.value = false
  }
}

async function handlePublish() {
  publishLoading.value = true
  try {
    await publishContract(contractId.value)
    message.success('合约已发布，等待自由职业者接单')
    await fetchContractDetail()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '发布合约失败')
  } finally {
    publishLoading.value = false
  }
}

async function handleSubmitAcceptance() {
  // 提交验收 - 跳转到验收报告页
  router.push(`/contract/${contractId.value}/report`)
}

async function handleTerminate() {
  terminateLoading.value = true
  try {
    await terminateContract(contractId.value)
    message.success('合约已终止')
    await fetchContractDetail()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '终止合约失败')
  } finally {
    terminateLoading.value = false
  }
}

function handleDownloadDeliverable(deliverable: Deliverable) {
  if (deliverable.file_url) {
    window.open(deliverable.file_url, '_blank')
  } else {
    message.warning('文件链接不可用')
  }
}

// ---------- 初始化 ----------
onMounted(async () => {
  await Promise.all([fetchContractDetail(), fetchDeliverables()])
})
</script>

<template>
  <div class="deliverables-page">
    <!-- 面包屑导航 -->
    <NBreadcrumb style="margin-bottom: 16px">
      <NBreadcrumbItem @click="router.push('/')">
        <NIcon :component="ArrowBackOutline" style="margin-right: 4px" />
        雇主首页
      </NBreadcrumbItem>
      <NBreadcrumbItem>合约详情</NBreadcrumbItem>
    </NBreadcrumb>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-container">
      <NSpin size="large" />
      <p class="loading-text">加载合约信息...</p>
    </div>

    <!-- 错误状态 -->
    <NResult
      v-else-if="error"
      status="error"
      title="加载失败"
      :description="error"
      style="margin-top: 60px"
    >
      <template #footer>
        <NButton @click="fetchContractDetail">重试</NButton>
      </template>
    </NResult>

    <!-- 正常内容 -->
    <template v-else-if="contract">
      <!-- 合约基本信息 -->
      <NCard title="合约信息" style="margin-bottom: 20px">
        <NDescriptions bordered :column="2">
          <NDescriptionsItem label="合约ID">
            <NText code>{{ contract.id }}</NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="状态">
            <NTag v-if="contractStatus" :type="contractStatus.type" round>
              {{ contractStatus.label }}
            </NTag>
          </NDescriptionsItem>
          <NDescriptionsItem label="任务名称" :span="2">
            <NText strong style="font-size: 16px">{{ contract.title || '未命名任务' }}</NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="任务描述" :span="2">
            <NText>{{ contract.description || '暂无描述' }}</NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="预算">
            <NText type="warning" strong style="font-size: 18px">
              ¥ {{ contract.budget?.toLocaleString() || '0' }}
            </NText>
          </NDescriptionsItem>
          <NDescriptionsItem label="截止日期">
            {{ contract.deadline ? formatDate(contract.deadline) : '未设置' }}
          </NDescriptionsItem>
          <NDescriptionsItem label="创建时间">
            {{ formatDate(contract.created_at) }}
          </NDescriptionsItem>
          <NDescriptionsItem label="更新时间">
            {{ formatDate(contract.updated_at) }}
          </NDescriptionsItem>
          <NDescriptionsItem label="验收标准" :span="2">
            <NText style="white-space: pre-wrap">{{ contract.acceptance_criteria || '暂未设置' }}</NText>
          </NDescriptionsItem>
        </NDescriptions>
      </NCard>

      <!-- 统计卡片 -->
      <NGrid :cols="3" :x-gap="16" :y-gap="16" style="margin-bottom: 20px">
        <NGi>
          <NCard hoverable>
            <NStatistic label="交付物数量" :value="deliverables.length" />
          </NCard>
        </NGi>
        <NGi>
          <NCard hoverable>
            <NStatistic label="合约状态">
              <template #default>
                <NTag v-if="contractStatus" :type="contractStatus.type" size="large" round>
                  {{ contractStatus.label }}
                </NTag>
              </template>
            </NStatistic>
          </NCard>
        </NGi>
        <NGi>
          <NCard hoverable>
            <NStatistic label="预算金额">
              <template #default>
                <NText type="warning" strong style="font-size: 24px">
                  ¥ {{ contract.budget?.toLocaleString() || '0' }}
                </NText>
              </template>
            </NStatistic>
          </NCard>
        </NGi>
      </NGrid>

      <!-- 交付物列表 -->
      <NCard title="交付物列表" style="margin-bottom: 20px">
        <template #header-extra>
          <NText depth="3">共 {{ deliverables.length }} 个交付物</NText>
        </template>

        <!-- 加载中 -->
        <div v-if="deliverablesLoading" class="loading-container">
          <NSpin size="medium" />
          <p class="loading-text">加载交付物...</p>
        </div>

        <!-- 空状态 -->
        <NEmpty
          v-else-if="deliverables.length === 0"
          description="暂无交付物"
          style="padding: 40px 0"
        >
          <template #extra>
            <NText depth="3">
              等待自由职业者提交交付物后，将在此显示
            </NText>
          </template>
        </NEmpty>

        <!-- 交付物列表 -->
        <NList v-else bordered hoverable>
          <NListItem v-for="item in deliverables" :key="item.id">
            <template #prefix>
              <NIcon :component="DocumentTextOutline" :size="24" color="#2080f0" />
            </template>
            <NSpace vertical :size="4" style="width: 100%">
              <NSpace justify="space-between" align="center" style="width: 100%">
                <NText strong>{{ item.file_name || '未命名文件' }}</NText>
                <NSpace :size="8">
                  <NTag type="info" size="small">
                    <template #icon>
                      <NIcon :component="TimeOutline" />
                    </template>
                    {{ formatDate(item.submitted_at) }}
                  </NTag>
                  <NButton
                    size="small"
                    quaternary
                    type="primary"
                    @click="handleDownloadDeliverable(item)"
                  >
                    <template #icon>
                      <NIcon :component="CloudDownloadOutline" />
                    </template>
                    下载
                  </NButton>
                </NSpace>
              </NSpace>
              <NText depth="3" v-if="item.description">{{ item.description }}</NText>
            </NSpace>
          </NListItem>
        </NList>
      </NCard>

      <!-- 操作按钮区 -->
      <NCard title="操作">
        <NSpace :size="12">
          <!-- 发布合约（草稿状态） -->
          <NPopconfirm v-if="canPublish" @positive-click="handlePublish">
            <template #trigger>
              <NButton type="primary" :loading="publishLoading">
                <template #icon>
                  <NIcon :component="SendOutline" />
                </template>
                发布合约
              </NButton>
            </template>
            确定发布此合约？发布后将进入市场等待自由职业者接单。
          </NPopconfirm>

          <!-- 提交验收 -->
          <NButton
            v-if="canSubmitAcceptance"
            type="success"
            @click="handleSubmitAcceptance"
          >
            <template #icon>
              <NIcon :component="CheckmarkCircleOutline" />
            </template>
            查看验收报告
          </NButton>

          <!-- 终止合约 -->
          <NPopconfirm v-if="canTerminate" @positive-click="handleTerminate">
            <template #trigger>
              <NButton type="error" :loading="terminateLoading" quaternary>
                <template #icon>
                  <NIcon :component="CloseCircleOutline" />
                </template>
                终止合约
              </NButton>
            </template>
            <NText type="error">警告：终止合约后将无法恢复，确定继续？</NText>
          </NPopconfirm>

          <!-- 返回 -->
          <NButton @click="router.push('/')">
            <template #icon>
              <NIcon :component="ArrowBackOutline" />
            </template>
            返回首页
          </NButton>
        </NSpace>

        <!-- 提示信息 -->
        <NAlert
          v-if="contract.status === 'draft'"
          type="info"
          style="margin-top: 16px"
        >
          此合约处于草稿状态，请先发布合约以让自由职业者接单
        </NAlert>
        <NAlert
          v-else-if="contract.status === 'pending_accept'"
          type="warning"
          style="margin-top: 16px"
        >
          合约已发布，等待自由职业者接单中
        </NAlert>
        <NAlert
          v-else-if="contract.status === 'completed'"
          type="success"
          style="margin-top: 16px"
        >
          合约已完成，感谢使用 OpenWork 平台
        </NAlert>
        <NAlert
          v-else-if="contract.status === 'cancelled'"
          type="default"
          style="margin-top: 16px"
        >
          此合约已终止
        </NAlert>
      </NCard>
    </template>
  </div>
</template>

<style scoped>
.deliverables-page {
  max-width: 1000px;
  margin: 0 auto;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}

.loading-text {
  margin-top: 12px;
  color: #999;
  font-size: 14px;
}
</style>
