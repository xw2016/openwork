<!-- P6 任务详情页 - 完整任务信息 + 意图蓝图 + 状态时间线 + 操作按钮 -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NH2, NText, NButton, NSpace, NTag, NDescriptions,
  NDescriptionsItem, NAlert, NSpin, NTimeline, NTimelineItem,
  NSteps, NStep, NDivider, NModal, NInput, NInputNumber, NResult
} from 'naive-ui'
import { getTaskDetail, bidTask } from '@/api/market'
import { acceptContract } from '@/api/contract'
import { useUserStore } from '@/stores/user'
import type { Contract, ContractStatus } from '@/types'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const userStore = useUserStore()

const taskId = route.params.id as string
const task = ref<Contract | null>(null)
const loading = ref(true)
const error = ref('')
const bidding = ref(false)
const accepting = ref(false)
const showBidModal = ref(false)
const bidProposal = ref('')
const bidPrice = ref<number | null>(null)

// 状态中文映射
const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  pending_accept: '待接单',
  in_progress: '进行中',
  submitted: '已提交交付物',
  reviewing: 'AI验收中',
  completed: '已完成',
  disputed: '争议中',
  cancelled: '已取消'
}

const statusColorMap: Record<string, string> = {
  draft: 'default',
  pending_accept: 'info',
  in_progress: 'warning',
  submitted: 'warning',
  reviewing: 'warning',
  completed: 'success',
  disputed: 'error',
  cancelled: 'default'
}

// 状态流转顺序（用于步骤条）
const statusOrder: ContractStatus[] = [
  'pending_accept', 'in_progress', 'submitted', 'reviewing', 'completed'
]

const currentStep = computed(() => {
  if (!task.value) return 0
  const idx = statusOrder.indexOf(task.value.status)
  return idx >= 0 ? idx : 0
})

const isCancelled = computed(() => task.value?.status === 'cancelled' || task.value?.status === 'disputed')

// 时间线数据
const timelineData = computed(() => {
  if (!task.value) return []
  const items = [
    {
      type: 'info' as const,
      title: '任务创建',
      content: `任务「${task.value.title}」已发布`,
      time: task.value.created_at
    }
  ]
  const s = task.value.status
  if (['in_progress', 'submitted', 'reviewing', 'completed'].includes(s)) {
    items.push({
      type: 'success' as const,
      title: '已接单',
      content: '自由职业者已接受任务',
      time: task.value.updated_at
    })
  }
  if (['submitted', 'reviewing', 'completed'].includes(s)) {
    items.push({
      type: 'warning' as const,
      title: '已提交交付物',
      content: '交付物已提交，等待验收',
      time: task.value.updated_at
    })
  }
  if (['reviewing', 'completed'].includes(s)) {
    items.push({
      type: 'warning' as const,
      title: 'AI验收中',
      content: '智能合约正在验证交付物质量',
      time: task.value.updated_at
    })
  }
  if (s === 'completed') {
    items.push({
      type: 'success' as const,
      title: '已完成',
      content: '验收通过，资金已释放',
      time: task.value.updated_at
    })
  }
  if (s === 'cancelled') {
    items.push({
      type: 'error' as const,
      title: '已取消',
      content: '任务已取消',
      time: task.value.updated_at
    })
  }
  if (s === 'disputed') {
    items.push({
      type: 'error' as const,
      title: '争议中',
      content: '任务存在争议，等待处理',
      time: task.value.updated_at
    })
  }
  return items
})

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '未设置'
  return new Date(dateStr).toLocaleString('zh-CN')
}

async function loadTask() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await getTaskDetail(taskId)
    task.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载任务详情失败'
  } finally {
    loading.value = false
  }
}

function openBidModal() {
  bidProposal.value = ''
  bidPrice.value = task.value?.budget || null
  showBidModal.value = true
}

async function handleBid() {
  if (!task.value) return
  bidding.value = true
  try {
    await bidTask(taskId, {
      proposal: bidProposal.value || undefined,
      price: bidPrice.value ?? undefined
    })
    message.success('竞标成功！已接单')
    showBidModal.value = false
    await loadTask()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '竞标失败，请重试')
  } finally {
    bidding.value = false
  }
}

async function handleAccept() {
  if (!task.value) return
  accepting.value = true
  try {
    await acceptContract(taskId)
    message.success('合约已接受！')
    await loadTask()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '接受合约失败')
  } finally {
    accepting.value = false
  }
}

function goToUpload() {
  router.push(`/task/${taskId}/upload`)
}

function goToAcceptance() {
  router.push(`/task/${taskId}/acceptance`)
}

onMounted(loadTask)
</script>

<template>
  <div class="task-detail-page">
    <NH2>任务详情</NH2>

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
        <NButton @click="loadTask">重试</NButton>
      </template>
    </NResult>

    <!-- 正常内容 -->
    <template v-else-if="task">
      <NSpace vertical :size="16">
        <!-- 状态提示 -->
        <NAlert
          v-if="task.status === 'pending_accept'"
          type="info"
          title="等待接单"
        >
          此任务正在等待自由职业者竞标接单，您可以通过下方按钮提交竞标方案。
        </NAlert>
        <NAlert
          v-else-if="task.status === 'in_progress'"
          type="warning"
          title="任务进行中"
        >
          此任务已被接单，正在进行中。完成后请上传交付物。
        </NAlert>
        <NAlert
          v-else-if="task.status === 'submitted' || task.status === 'reviewing'"
          type="warning"
          title="等待验收"
        >
          交付物已提交，正在进行AI智能验收。
        </NAlert>
        <NAlert
          v-else-if="task.status === 'completed'"
          type="success"
          title="任务已完成"
        >
          此任务已通过验收，资金已释放。
        </NAlert>

        <!-- 基本信息 -->
        <NCard title="基本信息">
          <NDescriptions bordered :column="2">
            <NDescriptionsItem label="任务ID">
              <NText code>{{ task.id }}</NText>
            </NDescriptionsItem>
            <NDescriptionsItem label="状态">
              <NTag :type="(statusColorMap[task.status] as any) || 'default'">
                {{ statusLabelMap[task.status] || task.status }}
              </NTag>
            </NDescriptionsItem>
            <NDescriptionsItem label="任务名称" :span="2">
              {{ task.title }}
            </NDescriptionsItem>
            <NDescriptionsItem label="预算">
              <NText type="warning" strong style="font-size:18px">
                ¥{{ task.budget.toFixed(2) }}
              </NText>
            </NDescriptionsItem>
            <NDescriptionsItem label="截止日期">
              {{ formatDate(task.deadline) }}
            </NDescriptionsItem>
            <NDescriptionsItem label="任务描述" :span="2">
              {{ task.description }}
            </NDescriptionsItem>
            <NDescriptionsItem label="创建时间">
              {{ formatDate(task.created_at) }}
            </NDescriptionsItem>
            <NDescriptionsItem label="更新时间">
              {{ formatDate(task.updated_at) }}
            </NDescriptionsItem>
          </NDescriptions>
        </NCard>

        <!-- 意图蓝图 & 验收标准 -->
        <NCard title="意图蓝图 & 验收标准">
          <NSpace vertical :size="16">
            <div>
              <NText strong style="display:block;margin-bottom:8px">AI 意图模型</NText>
              <NText style="white-space:pre-wrap;word-break:break-word">
                {{ task.intent_model || '暂未生成意图模型' }}
              </NText>
            </div>
            <NDivider />
            <div>
              <NText strong style="display:block;margin-bottom:8px">验收标准</NText>
              <NText style="white-space:pre-wrap;word-break:break-word">
                {{ task.acceptance_criteria || '暂未设置验收标准' }}
              </NText>
            </div>
          </NSpace>
        </NCard>

        <!-- 状态时间线 -->
        <NCard title="任务进度">
          <NTimeline>
            <NTimelineItem
              v-for="(item, index) in timelineData"
              :key="index"
              :type="item.type"
              :title="item.title"
              :content="item.content"
              :time="formatDate(item.time)"
            />
          </NTimeline>
        </NCard>

        <!-- 进度步骤条 -->
        <NCard v-if="!isCancelled" title="状态流转">
          <NSteps :current="currentStep + 1" size="small">
            <NStep title="待接单" />
            <NStep title="进行中" />
            <NStep title="已提交" />
            <NStep title="验收中" />
            <NStep title="已完成" />
          </NSteps>
        </NCard>

        <!-- 操作按钮 -->
        <NCard>
          <NSpace>
            <!-- 待接单：竞标接单 -->
            <template v-if="task.status === 'pending_accept'">
              <NButton type="primary" size="large" @click="openBidModal">
                竞标接单
              </NButton>
            </template>

            <!-- 进行中：上传交付物 -->
            <template v-else-if="task.status === 'in_progress'">
              <NButton type="primary" size="large" @click="goToUpload">
                上传交付物
              </NButton>
            </template>

            <!-- 已提交/验收中：查看验收 -->
            <template v-else-if="task.status === 'submitted' || task.status === 'reviewing'">
              <NButton type="primary" size="large" @click="goToAcceptance">
                查看验收结果
              </NButton>
            </template>

            <!-- 已完成 -->
            <template v-else-if="task.status === 'completed'">
              <NButton type="success" size="large" disabled>
                任务已完成
              </NButton>
            </template>

            <NButton size="large" @click="router.back()">返回</NButton>
          </NSpace>
        </NCard>
      </NSpace>
    </template>

    <!-- 竞标弹窗 -->
    <NModal
      v-model:show="showBidModal"
      preset="card"
      title="竞标接单"
      style="max-width:500px"
    >
      <NSpace vertical :size="16">
        <div>
          <NText strong style="display:block;margin-bottom:8px">竞标方案</NText>
          <NInput
            v-model:value="bidProposal"
            type="textarea"
            placeholder="请描述您的执行方案、相关经验等（可选）"
            :rows="4"
          />
        </div>
        <div>
          <NText strong style="display:block;margin-bottom:8px">报价（元）</NText>
          <NInputNumber
            v-model:value="bidPrice"
            :min="0"
            placeholder="输入您的报价"
            style="width:100%"
          >
            <template #prefix>¥</template>
          </NInputNumber>
        </div>
        <NAlert type="info">
          竞标成功后将自动创建合约，请确认您的方案和报价。
        </NAlert>
      </NSpace>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showBidModal = false">取消</NButton>
          <NButton type="primary" :loading="bidding" @click="handleBid">
            确认竞标
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.task-detail-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}
</style>
