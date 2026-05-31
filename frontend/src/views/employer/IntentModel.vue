// P2 AI 意图建模页 - 多步骤向导
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard,
  NButton,
  NSpace,
  NInput,
  NRadioGroup,
  NRadio,
  NTag,
  NList,
  NListItem,
  NAlert,
  NSpin,
  NSteps,
  NStep,
  NDivider,
  NText,
  NIcon,
  NResult,
} from 'naive-ui'
import {
  AnalyticsOutline,
  CheckmarkCircleOutline,
  ArrowBackOutline,
  ArrowForwardOutline,
} from '@vicons/ionicons5'
import {
  analyzeIntent,
  getBlueprint,
  updateBlueprint,
  lockBlueprint,
  submitQuestionAnswer,
  skipQuestion,
} from '@/api/intent'
import type { IntentAnalyzeResponse, IntentQuestion, IntentBlueprint } from '@/api/intent'
import { createContract } from '@/api/contract'

const router = useRouter()
const route = useRoute()
const message = useMessage()

// ---------- 步骤状态 ----------
const currentStep = ref(1)

// ---------- Step 1: 任务描述输入 ----------
const description = ref('')
const category = ref('')
const analyzeLoading = ref(false)

// ---------- Step 2: AI 分析结果 ----------
const analysisResult = ref<IntentAnalyzeResponse | null>(null)

// ---------- Step 3: 追问回答 ----------
const questions = ref<IntentQuestion[]>([])
const currentQuestionIndex = ref(0)
const selectedAnswer = ref('')
const questionSubmitting = ref(false)

// ---------- Step 4: 蓝图预览 ----------
const blueprint = ref<IntentBlueprint | null>(null)
const blueprintLoading = ref(false)
const budget = ref<number | null>(null)
const deadline = ref('')

// ---------- Step 5: 确认锁定 ----------
const lockLoading = ref(false)
const locked = ref(false)

// ---------- 是否已有 blueprintId（从路由参数恢复） ----------
const existingBlueprintId = computed(() => route.params.id as string | undefined)

// ---------- 当前追问 ----------
const currentQuestion = computed(() => {
  if (questions.value.length === 0) return null
  return questions.value[currentQuestionIndex.value] || null
})

const hasMoreQuestions = computed(() => {
  return currentQuestionIndex.value < questions.value.length - 1
})

// ---------- Step 1: 分析意图 ----------
async function handleAnalyze() {
  if (!description.value.trim()) {
    message.warning('请输入任务描述')
    return
  }
  analyzeLoading.value = true
  try {
    const { data: res } = await analyzeIntent({
      user_input: description.value.trim(),
      context: category.value ? { category: category.value } : undefined,
    })
    const result = (res as any).data ?? res
    analysisResult.value = result
    questions.value = result.questions || []
    currentQuestionIndex.value = 0
    currentStep.value = 2
    message.success('AI 分析完成')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'AI 分析失败，请稍后重试')
  } finally {
    analyzeLoading.value = false
  }
}

// ---------- Step 2 → Step 3: 进入追问 ----------
function goToQuestions() {
  if (questions.value.length === 0) {
    // 没有追问，直接跳到蓝图预览
    saveBlueprintAndPreview()
    return
  }
  currentStep.value = 3
  currentQuestionIndex.value = 0
  selectedAnswer.value = ''
}

// ---------- Step 3: 提交追问答案 ----------
async function handleSubmitAnswer() {
  if (!currentQuestion.value) return
  if (!selectedAnswer.value) {
    message.warning('请选择一个选项')
    return
  }

  questionSubmitting.value = true
  try {
    await submitQuestionAnswer(
      analysisResult.value?.blueprint_id || '',
      currentQuestion.value.id,
      selectedAnswer.value
    )
    message.success('答案已提交')

    // 移到下一题或进入预览
    if (hasMoreQuestions.value) {
      currentQuestionIndex.value++
      selectedAnswer.value = ''
    } else {
      await saveBlueprintAndPreview()
    }
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '提交答案失败')
  } finally {
    questionSubmitting.value = false
  }
}

// ---------- Step 3: 跳过追问 ----------
async function handleSkipQuestion() {
  if (!currentQuestion.value) return

  questionSubmitting.value = true
  try {
    await skipQuestion(currentQuestion.value.id)
    message.info('已跳过该问题')

    if (hasMoreQuestions.value) {
      currentQuestionIndex.value++
      selectedAnswer.value = ''
    } else {
      await saveBlueprintAndPreview()
    }
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '跳过失败')
  } finally {
    questionSubmitting.value = false
  }
}

// ---------- 保存蓝图并预览 ----------
async function saveBlueprintAndPreview() {
  blueprintLoading.value = true
  try {
    const blueprintId = analysisResult.value?.blueprint_id
    if (blueprintId) {
      // 获取最新的蓝图
      const { data: res } = await getBlueprint(blueprintId)
      blueprint.value = (res as any).data ?? res
    }
    currentStep.value = 4
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '获取蓝图失败')
  } finally {
    blueprintLoading.value = false
  }
}

// ---------- Step 4 → Step 5: 锁定蓝图 ----------
async function handleLockBlueprint() {
  if (!blueprint.value) return

  lockLoading.value = true
  try {
    // 先更新预算和截止日期
    if (budget.value || deadline.value) {
      await updateBlueprint(blueprint.value.id, {
        // 额外信息通过 description 或扩展字段传递
      })
    }

    await lockBlueprint(blueprint.value.id)
    locked.value = true
    currentStep.value = 5
    message.success('蓝图已锁定')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '锁定蓝图失败')
  } finally {
    lockLoading.value = false
  }
}

// ---------- Step 5: 创建合约并跳转 ----------
async function handleCreateContract() {
  if (!blueprint.value) return

  try {
    const { data: res } = await createContract({
      title: blueprint.value.title,
      description: blueprint.value.description,
      budget: budget.value || 0,
      intent_model: blueprint.value.id,
      acceptance_criteria: blueprint.value.acceptance_criteria,
    })
    const contractData = (res as any).data ?? res
    message.success('合约创建成功')
    router.push(`/employer/deliverables/${contractData.id}`)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '创建合约失败')
  }
}

// ---------- 初始化：检查路由参数恢复状态 ----------
onMounted(async () => {
  if (existingBlueprintId.value) {
    blueprintLoading.value = true
    try {
      const { data: res } = await getBlueprint(existingBlueprintId.value)
      const bp = (res as any).data ?? res
      blueprint.value = bp
      if (bp.status === 'locked') {
        locked.value = true
        currentStep.value = 5
      } else {
        currentStep.value = 4
      }
    } catch {
      // 蓝图不存在，从头开始
    } finally {
      blueprintLoading.value = false
    }
  }
})

// ---------- 步骤标题 ----------
const stepTitles = ['描述任务', 'AI 分析结果', '回答追问', '预览蓝图', '确认创建']
</script>

<template>
  <div class="intent-model">
    <h2 class="page-title">AI 意图建模</h2>
    <p class="page-subtitle">通过 AI 分析您的需求，自动生成结构化任务描述和验收标准</p>

    <!-- 步骤条 -->
    <NCard style="margin-bottom: 20px">
      <NSteps :current="currentStep" :status="'process'" size="small">
        <NStep v-for="(title, idx) in stepTitles" :key="idx" :title="title" />
      </NSteps>
    </NCard>

    <!-- Step 1: 任务描述输入 -->
    <NCard v-if="currentStep === 1" title="描述您的任务需求">
      <NSpace vertical :size="20">
        <div>
          <NText strong style="display: block; margin-bottom: 8px">任务描述 *</NText>
          <NInput
            v-model:value="description"
            type="textarea"
            :rows="6"
            placeholder="请详细描述您的任务需求，包括：&#10;1. 具体要完成什么工作&#10;2. 功能要求和技术偏好&#10;3. 设计风格或质量标准&#10;4. 任何特殊要求"
            :maxlength="5000"
            show-count
          />
        </div>
        <div>
          <NText strong style="display: block; margin-bottom: 8px">任务分类（可选）</NText>
          <NInput
            v-model:value="category"
            placeholder="例如：网站开发、UI设计、文案撰写..."
            style="max-width: 400px"
          />
        </div>
        <NSpace>
          <NButton
            type="primary"
            size="large"
            :loading="analyzeLoading"
            :disabled="!description.trim()"
            @click="handleAnalyze"
          >
            <template #icon>
              <NIcon :component="AnalyticsOutline" />
            </template>
            AI 分析意图
          </NButton>
          <NButton size="large" @click="router.back()">取消</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <!-- Step 2: AI 分析结果 -->
    <NCard v-if="currentStep === 2" title="AI 分析结果">
      <template v-if="analysisResult">
        <NSpace vertical :size="20">
          <!-- 置信度 -->
          <NAlert :type="analysisResult.confidence >= 0.7 ? 'success' : 'warning'" closable>
            <template #header>
              分析置信度：{{ Math.round(analysisResult.confidence * 100) }}%
            </template>
            <template v-if="analysisResult.confidence < 0.7">
              AI 对需求的理解可能不够完整，建议通过追问环节补充信息
            </template>
            <template v-else>
              AI 已较好地理解了您的需求
            </template>
          </NAlert>

          <!-- 任务类型 -->
          <div>
            <NText strong style="display: block; margin-bottom: 8px">任务类型</NText>
            <NTag type="info" size="large" round>{{ analysisResult.task_type }}</NTag>
          </div>

          <!-- 需求列表 -->
          <div>
            <NText strong style="display: block; margin-bottom: 8px">识别的需求</NText>
            <NList bordered hoverable>
              <NListItem v-for="(req, idx) in analysisResult.requirements" :key="idx">
                <NText>{{ idx + 1 }}. {{ req }}</NText>
              </NListItem>
            </NList>
          </div>

          <!-- 特殊注意点 -->
          <div v-if="analysisResult.quirks && analysisResult.quirks.length > 0">
            <NText strong style="display: block; margin-bottom: 8px">特殊注意点</NText>
            <NSpace>
              <NTag v-for="(quirk, idx) in analysisResult.quirks" :key="idx" type="warning">
                {{ quirk }}
              </NTag>
            </NSpace>
          </div>

          <!-- 追问数量提示 -->
          <NAlert v-if="questions.length > 0" type="info">
            AI 还有 {{ questions.length }} 个追问需要确认，以更精准地理解您的需求
          </NAlert>
          <NAlert v-else type="success">
            AI 已充分理解您的需求，可以直接生成蓝图
          </NAlert>

          <NDivider />

          <NSpace>
            <NButton type="primary" size="large" @click="goToQuestions">
              <template #icon>
                <NIcon :component="ArrowForwardOutline" />
              </template>
              {{ questions.length > 0 ? '回答追问' : '生成蓝图' }}
            </NButton>
            <NButton size="large" @click="currentStep = 1">
              <template #icon>
                <NIcon :component="ArrowBackOutline" />
              </template>
              返回修改
            </NButton>
          </NSpace>
        </NSpace>
      </template>
    </NCard>

    <!-- Step 3: 追问回答 -->
    <NCard v-if="currentStep === 3" :title="`追问 ${currentQuestionIndex + 1} / ${questions.length}`">
      <template v-if="currentQuestion">
        <NSpace vertical :size="20">
          <!-- 进度提示 -->
          <NAlert type="info">
            <template #header>
              问题 {{ currentQuestionIndex + 1 }} / {{ questions.length }}
            </template>
            优先级：{{ currentQuestion.priority }} / 5
            <template v-if="currentQuestion.skip_rate > 0">
              · 跳过率：{{ Math.round(currentQuestion.skip_rate * 100) }}%
            </template>
          </NAlert>

          <!-- 问题内容 -->
          <NText strong style="font-size: 16px; display: block; margin-bottom: 12px">
            {{ currentQuestion.question }}
          </NText>

          <!-- 选项 -->
          <NRadioGroup v-model:value="selectedAnswer" :disabled="questionSubmitting">
            <NSpace vertical :size="12">
              <NRadio
                v-for="(option, idx) in currentQuestion.options"
                :key="idx"
                :value="option"
                style="padding: 8px 0"
              >
                {{ option }}
              </NRadio>
            </NSpace>
          </NRadioGroup>

          <NDivider />

          <NSpace>
            <NButton
              type="primary"
              :loading="questionSubmitting"
              :disabled="!selectedAnswer"
              @click="handleSubmitAnswer"
            >
              <template #icon>
                <NIcon :component="ArrowForwardOutline" />
              </template>
              {{ hasMoreQuestions ? '下一题' : '提交并生成蓝图' }}
            </NButton>
            <NButton
              :loading="questionSubmitting"
              @click="handleSkipQuestion"
            >
              跳过此题
            </NButton>
          </NSpace>
        </NSpace>
      </template>
    </NCard>

    <!-- Step 4: 蓝图预览 -->
    <NCard v-if="currentStep === 4" title="蓝图预览">
      <template v-if="blueprintLoading">
        <div class="loading-container">
          <NSpin size="large" />
          <p class="loading-text">生成蓝图中...</p>
        </div>
      </template>
      <template v-else-if="blueprint">
        <NSpace vertical :size="20">
          <!-- 基本信息 -->
          <div>
            <NText strong style="display: block; margin-bottom: 8px">任务名称</NText>
            <NText style="font-size: 18px">{{ blueprint.title }}</NText>
          </div>

          <div>
            <NText strong style="display: block; margin-bottom: 8px">任务描述</NText>
            <NText>{{ blueprint.description }}</NText>
          </div>

          <div>
            <NText strong style="display: block; margin-bottom: 8px">任务类型</NText>
            <NTag type="info">{{ blueprint.task_type }}</NTag>
          </div>

          <!-- 需求列表 -->
          <div>
            <NText strong style="display: block; margin-bottom: 8px">需求清单</NText>
            <NList bordered>
              <NListItem v-for="(req, idx) in blueprint.requirements" :key="idx">
                <NText>{{ idx + 1 }}. {{ req }}</NText>
              </NListItem>
            </NList>
          </div>

          <!-- 验收标准 -->
          <div>
            <NText strong style="display: block; margin-bottom: 8px">验收标准</NText>
            <NCard embedded>
              <NText style="white-space: pre-wrap">{{ blueprint.acceptance_criteria }}</NText>
            </NCard>
          </div>

          <!-- 特殊注意点 -->
          <div v-if="blueprint.quirks && blueprint.quirks.length > 0">
            <NText strong style="display: block; margin-bottom: 8px">特殊注意点</NText>
            <NSpace>
              <NTag v-for="(quirk, idx) in blueprint.quirks" :key="idx" type="warning">
                {{ quirk }}
              </NTag>
            </NSpace>
          </div>

          <!-- 补充信息 -->
          <NAlert type="info" closable>
            请确认以上信息无误后，点击「锁定蓝图」进入合约创建流程
          </NAlert>

          <NDivider />

          <NSpace>
            <NButton
              type="primary"
              size="large"
              :loading="lockLoading"
              @click="handleLockBlueprint"
            >
              <template #icon>
                <NIcon :component="CheckmarkCircleOutline" />
              </template>
              锁定蓝图
            </NButton>
            <NButton size="large" @click="currentStep = 1">
              <template #icon>
                <NIcon :component="ArrowBackOutline" />
              </template>
              重新描述
            </NButton>
          </NSpace>
        </NSpace>
      </template>
    </NCard>

    <!-- Step 5: 确认创建合约 -->
    <NCard v-if="currentStep === 5" title="确认创建合约">
      <NResult status="success" title="蓝图已锁定" description="您的任务蓝图已成功锁定，可以创建合约发布了">
        <template #footer>
          <NSpace vertical :size="16" align="center">
            <NText depth="3">
              任务名称：{{ blueprint?.title || '--' }}
            </NText>
            <NSpace>
              <NButton type="primary" size="large" @click="handleCreateContract">
                创建合约并发布
              </NButton>
              <NButton size="large" @click="router.push('/')">
                返回首页
              </NButton>
            </NSpace>
          </NSpace>
        </template>
      </NResult>
    </NCard>
  </div>
</template>

<style scoped>
.intent-model {
  max-width: 900px;
  margin: 0 auto;
}

.page-title {
  margin: 0 0 4px 0;
  font-size: 24px;
  font-weight: 600;
}

.page-subtitle {
  margin: 0 0 20px 0;
  color: #999;
  font-size: 14px;
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
