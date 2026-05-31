<!-- P5 任务市场页 - 任务卡片网格 + 筛选 + 分页 -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NH2, NText, NButton, NSpace, NTag, NGrid, NGi,
  NInput, NSelect, NInputNumber, NPagination, NSpin, NEmpty,
  NDivider
} from 'naive-ui'
import { getMarketTasks } from '@/api/market'
import type { Contract } from '@/types'

const router = useRouter()
const message = useMessage()

// 列表数据
const tasks = ref<Contract[]>([])
const total = ref(0)
const loading = ref(false)

// 筛选条件
const page = ref(1)
const pageSize = ref(12)
const searchTitle = ref('')
const category = ref<string | null>(null)
const minBudget = ref<number | null>(null)
const maxBudget = ref<number | null>(null)
const statusFilter = ref<string | null>(null)

// 分类选项
const categoryOptions = [
  { label: '全部分类', value: '' },
  { label: '软件开发', value: 'development' },
  { label: '设计', value: 'design' },
  { label: '写作翻译', value: 'writing' },
  { label: '数据分析', value: 'data' },
  { label: '营销推广', value: 'marketing' },
  { label: '其他', value: 'other' }
]

// 状态选项
const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '待接单', value: 'pending_accept' },
  { label: '进行中', value: 'in_progress' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' }
]

// 状态标签颜色映射
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

// 状态中文映射
const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  pending_accept: '待接单',
  in_progress: '进行中',
  submitted: '已提交',
  reviewing: '验收中',
  completed: '已完成',
  disputed: '争议中',
  cancelled: '已取消'
}

async function loadTasks() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: page.value,
      page_size: pageSize.value
    }
    if (category.value) params.category = category.value
    if (minBudget.value != null) params.min_budget = minBudget.value
    if (maxBudget.value != null) params.max_budget = maxBudget.value
    if (statusFilter.value) params.status = statusFilter.value

    const { data } = await getMarketTasks(params)
    // 客户端按标题搜索过滤（如果API不支持搜索）
    let items = data.items || []
    if (searchTitle.value.trim()) {
      const keyword = searchTitle.value.trim().toLowerCase()
      items = items.filter(t => t.title.toLowerCase().includes(keyword))
    }
    tasks.value = items
    total.value = data.total
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载任务列表失败')
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function handlePageChange(p: number) {
  page.value = p
  loadTasks()
}

function handleSearch() {
  page.value = 1
  loadTasks()
}

function resetFilters() {
  searchTitle.value = ''
  category.value = null
  minBudget.value = null
  maxBudget.value = null
  statusFilter.value = null
  page.value = 1
  loadTasks()
}

function goToTask(id: string) {
  router.push(`/task/${id}`)
}

function formatDeadline(deadline: string | null): string {
  if (!deadline) return '无截止日期'
  return new Date(deadline).toLocaleDateString('zh-CN')
}

onMounted(loadTasks)
</script>

<template>
  <div class="market-page">
    <!-- 标题 -->
    <div class="page-header">
      <NH2 style="margin:0">任务市场</NH2>
      <NText depth="3">浏览可用的任务并竞标接单</NText>
    </div>

    <!-- 筛选区域 -->
    <NCard size="small" style="margin-bottom:16px">
      <NSpace vertical :size="12">
        <NSpace :size="12" wrap>
          <NInput
            v-model:value="searchTitle"
            placeholder="搜索任务标题"
            clearable
            style="width:240px"
            @keyup.enter="handleSearch"
          />
          <NSelect
            v-model:value="category"
            :options="categoryOptions"
            placeholder="选择分类"
            clearable
            style="width:160px"
          />
          <NSelect
            v-model:value="statusFilter"
            :options="statusOptions"
            placeholder="任务状态"
            clearable
            style="width:140px"
          />
          <NInputNumber
            v-model:value="minBudget"
            placeholder="最低预算"
            :min="0"
            clearable
            style="width:140px"
          >
            <template #prefix>¥</template>
          </NInputNumber>
          <NInputNumber
            v-model:value="maxBudget"
            placeholder="最高预算"
            :min="0"
            clearable
            style="width:140px"
          >
            <template #prefix>¥</template>
          </NInputNumber>
        </NSpace>
        <NSpace :size="8">
          <NButton type="primary" @click="handleSearch">搜索</NButton>
          <NButton @click="resetFilters">重置筛选</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <!-- 加载中 -->
    <div v-if="loading" style="display:flex;justify-content:center;padding:80px 0">
      <NSpin size="large" />
    </div>

    <!-- 空状态 -->
    <NEmpty
      v-else-if="tasks.length === 0"
      description="暂无匹配的任务"
      style="margin-top:60px"
    >
      <template #extra>
        <NText depth="3">试试调整筛选条件</NText>
      </template>
    </NEmpty>

    <!-- 任务卡片网格 -->
    <template v-else>
      <NGrid :x-gap="16" :y-gap="16" :cols="4" responsive="screen" :item-responsive="true">
        <NGi v-for="task in tasks" :key="task.id" span="4 m:2 l:1">
          <NCard
            hoverable
            class="task-card"
            @click="goToTask(task.id)"
            style="cursor:pointer;height:100%"
          >
            <template #header>
              <NText strong style="font-size:15px;line-height:1.4">
                {{ task.title }}
              </NText>
            </template>
            <template #header-extra>
              <NTag :type="(statusColorMap[task.status] as any) || 'default'" size="small">
                {{ statusLabelMap[task.status] || task.status }}
              </NTag>
            </template>

            <NSpace vertical :size="8">
              <!-- 预算 -->
              <NSpace justify="space-between" align="center">
                <NText depth="3" style="font-size:13px">预算</NText>
                <NText type="warning" strong style="font-size:18px">
                  ¥{{ task.budget.toFixed(2) }}
                </NText>
              </NSpace>

              <!-- 描述预览 -->
              <NText depth="3" style="font-size:13px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">
                {{ task.description }}
              </NText>

              <NDivider style="margin:4px 0" />

              <!-- 底部信息 -->
              <NSpace justify="space-between" align="center">
                <NText depth="3" style="font-size:12px">
                  雇主信用: {{ task.employer_id ? '已认证' : '未认证' }}
                </NText>
                <NText depth="3" style="font-size:12px">
                  截止: {{ formatDeadline(task.deadline) }}
                </NText>
              </NSpace>
            </NSpace>
          </NCard>
        </NGi>
      </NGrid>

      <!-- 分页 -->
      <div v-if="total > pageSize" style="display:flex;justify-content:center;margin-top:24px">
        <NPagination
          v-model:page="page"
          :page-size="pageSize"
          :item-count="total"
          :on-update:page="handlePageChange"
          show-quick-jumper
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.market-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}
.page-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 16px;
}
.task-card {
  transition: box-shadow 0.2s, transform 0.2s;
}
.task-card:hover {
  transform: translateY(-2px);
}
</style>
