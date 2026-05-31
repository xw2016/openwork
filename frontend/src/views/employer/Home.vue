// P1 雇主首页 - 任务/合约列表仪表板
<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  NCard,
  NButton,
  NSpace,
  NGrid,
  NGi,
  NStatistic,
  NTabs,
  NTabPane,
  NInput,
  NTag,
  NSpin,
  NEmpty,
  NDataTable,
  NIcon,
  NPagination,
  NText,
} from 'naive-ui'
import { SearchOutline, AddOutline, DocumentTextOutline } from '@vicons/ionicons5'
import { getMyContracts } from '@/api/contract'
import type { Contract, ContractStatus } from '@/types'

const router = useRouter()
const message = useMessage()

// ---------- 状态 ----------
const loading = ref(false)
const contracts = ref<Contract[]>([])
const totalContracts = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const activeTab = ref<string>('all')
const searchText = ref('')

// ---------- 状态映射 ----------
const statusMap: Record<ContractStatus, { label: string; type: 'success' | 'warning' | 'info' | 'error' | 'default' }> = {
  draft: { label: '草稿', type: 'default' },
  pending_accept: { label: '待接单', type: 'warning' },
  in_progress: { label: '进行中', type: 'info' },
  submitted: { label: '已提交', type: 'warning' },
  reviewing: { label: 'AI验收中', type: 'info' },
  completed: { label: '已完成', type: 'success' },
  disputed: { label: '争议中', type: 'error' },
  cancelled: { label: '已取消', type: 'default' },
}

// Tab 对应的 status 过滤
const tabStatusMap: Record<string, string | undefined> = {
  all: undefined,
  draft: 'draft',
  in_progress: 'in_progress',
  completed: 'completed',
}

// ---------- 统计数据 ----------
const stats = computed(() => {
  const total = totalContracts.value
  const inProgressCount = contracts.value.filter(
    (c) => c.status === 'in_progress' || c.status === 'submitted' || c.status === 'reviewing'
  ).length
  const completedCount = contracts.value.filter((c) => c.status === 'completed').length
  const draftCount = contracts.value.filter((c) => c.status === 'draft').length
  return { total, inProgressCount, completedCount, draftCount }
})

// ---------- 搜索过滤后的数据 ----------
const filteredContracts = computed(() => {
  if (!searchText.value) return contracts.value
  const keyword = searchText.value.toLowerCase()
  return contracts.value.filter(
    (c) =>
      c.title.toLowerCase().includes(keyword) ||
      c.description.toLowerCase().includes(keyword)
  )
})

// ---------- 表格列定义 ----------
const columns: DataTableColumns<Contract> = [
  {
    title: '任务名称',
    key: 'title',
    ellipsis: { tooltip: true },
    render(row) {
      return row.title || '未命名任务'
    },
  },
  {
    title: '预算',
    key: 'budget',
    width: 120,
    align: 'right',
    render(row) {
      return `¥ ${row.budget.toLocaleString()}`
    },
  },
  {
    title: '状态',
    key: 'status',
    width: 110,
    align: 'center',
    render(row) {
      const info = statusMap[row.status] || { label: row.status, type: 'default' as const }
      return h(NTag, { type: info.type, size: 'small', round: true }, { default: () => info.label })
    },
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
    render(row) {
      return formatDate(row.created_at)
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    align: 'center',
    render(row) {
      return h(
        NButton,
        {
          size: 'small',
          type: 'primary',
          quaternary: true,
          onClick: () => router.push(`/employer/deliverables/${row.id}`),
        },
        { default: () => '查看详情' }
      )
    },
  },
]

// ---------- API 调用 ----------
async function fetchContracts() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    const statusFilter = tabStatusMap[activeTab.value]
    if (statusFilter) {
      params.status = statusFilter
    }
    const { data } = await getMyContracts(params)
    contracts.value = data.items || []
    totalContracts.value = data.total || 0
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '加载任务列表失败')
  } finally {
    loading.value = false
  }
}

// ---------- 事件处理 ----------
function handleTabChange(tab: string) {
  activeTab.value = tab
  currentPage.value = 1
  fetchContracts()
}

function handlePageChange(page: number) {
  currentPage.value = page
  fetchContracts()
}

function handleSearch() {
  // 搜索是前端过滤，无需重新请求
}

function goToCreate() {
  router.push('/employer/intent-model')
}

// ---------- 工具函数 ----------
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

// ---------- 初始化 ----------
onMounted(() => {
  fetchContracts()
})
</script>

<template>
  <div class="employer-home">
    <!-- 顶部标题栏 -->
    <div class="page-header">
      <h2 class="page-title">雇主工作台</h2>
      <NButton type="primary" size="large" @click="goToCreate">
        <template #icon>
          <NIcon :component="AddOutline" />
        </template>
        发布新任务
      </NButton>
    </div>

    <!-- 统计卡片 -->
    <NGrid :cols="4" :x-gap="16" :y-gap="16" responsive="screen" :item-responsive="true">
      <NGi span="4 m:1">
        <NCard hoverable class="stat-card">
          <NStatistic label="全部任务" :value="stats.total">
            <template #prefix>
              <NIcon :component="DocumentTextOutline" />
            </template>
          </NStatistic>
        </NCard>
      </NGi>
      <NGi span="4 m:1">
        <NCard hoverable class="stat-card">
          <NStatistic label="草稿" :value="stats.draftCount" />
        </NCard>
      </NGi>
      <NGi span="4 m:1">
        <NCard hoverable class="stat-card stat-card--active">
          <NStatistic label="进行中" :value="stats.inProgressCount">
            <template #suffix>
              <NTag type="info" size="small" round>活跃</NTag>
            </template>
          </NStatistic>
        </NCard>
      </NGi>
      <NGi span="4 m:1">
        <NCard hoverable class="stat-card stat-card--done">
          <NStatistic label="已完成" :value="stats.completedCount">
            <template #suffix>
              <NTag type="success" size="small" round>完成</NTag>
            </template>
          </NStatistic>
        </NCard>
      </NGi>
    </NGrid>

    <!-- 搜索 + 筛选 -->
    <NCard style="margin-top: 20px">
      <NSpace justify="space-between" align="center" style="margin-bottom: 16px">
        <NTabs
          :value="activeTab"
          type="line"
          @update:value="handleTabChange"
        >
          <NTabPane name="all" tab="全部" />
          <NTabPane name="draft" tab="草稿" />
          <NTabPane name="in_progress" tab="进行中" />
          <NTabPane name="completed" tab="已完成" />
        </NTabs>
        <NInput
          v-model:value="searchText"
          placeholder="搜索任务名称..."
          clearable
          style="width: 240px"
          @update:value="handleSearch"
        >
          <template #prefix>
            <NIcon :component="SearchOutline" />
          </template>
        </NInput>
      </NSpace>

      <!-- 加载中 -->
      <div v-if="loading" class="loading-container">
        <NSpin size="large" />
        <p class="loading-text">加载中...</p>
      </div>

      <!-- 空状态 -->
      <NEmpty
        v-else-if="filteredContracts.length === 0"
        description="暂无任务"
        style="padding: 60px 0"
      >
        <template #extra>
          <NText depth="3">点击「发布新任务」开始创建您的第一个任务</NText>
        </template>
      </NEmpty>

      <!-- 任务表格 -->
      <template v-else>
        <NDataTable
          :columns="columns"
          :data="filteredContracts"
          :bordered="false"
          :single-line="false"
          striped
          :row-key="(row: Contract) => row.id"
          @click-row="(row: Contract) => router.push(`/employer/deliverables/${row.id}`)"
          style="cursor: pointer"
        />

        <!-- 分页 -->
        <div v-if="totalContracts > pageSize" class="pagination-wrapper">
          <NPagination
            :page="currentPage"
            :page-count="Math.ceil(totalContracts / pageSize)"
            :page-size="pageSize"
            @update:page="handlePageChange"
          />
        </div>
      </template>
    </NCard>
  </div>
</template>

<style scoped>
.employer-home {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.stat-card {
  transition: box-shadow 0.3s ease;
}

.stat-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.stat-card--active {
  border-left: 3px solid #2080f0;
}

.stat-card--done {
  border-left: 3px solid #18a058;
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

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--n-border-color, #efeff5);
}
</style>
