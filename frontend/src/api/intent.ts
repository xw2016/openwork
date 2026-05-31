// AI 意图建模 API
import http from './index'

/** 意图分析请求 */
export interface IntentAnalyzeRequest {
  user_input: string
  context?: Record<string, any>
}

/** 意图分析响应 */
export interface IntentAnalyzeResponse {
  blueprint_id: string
  task_type: string
  requirements: string[]
  questions: IntentQuestion[]
  quirks: string[]
  confidence: number
}

/** 追问项 */
export interface IntentQuestion {
  id: string
  question: string
  options: string[]
  priority: number
  skip_rate: number
}

/** 蓝图 */
export interface IntentBlueprint {
  id: string
  user_id: string
  title: string
  description: string
  task_type: string
  requirements: string[]
  acceptance_criteria: string
  quirks: string[]
  status: 'draft' | 'locked' | 'published'
  created_at: string
  updated_at: string
}

/** 分析意图 */
export function analyzeIntent(data: IntentAnalyzeRequest) {
  return http.post<IntentAnalyzeResponse>('/v1/intent/analyze', data)
}

/** 保存蓝图 */
export function createBlueprint(data: Partial<IntentBlueprint>) {
  return http.post<IntentBlueprint>('/v1/intent/blueprint', data)
}

/** 获取蓝图详情 */
export function getBlueprint(blueprintId: string) {
  return http.get<IntentBlueprint>(`/v1/intent/blueprint/${blueprintId}`)
}

/** 更新蓝图 */
export function updateBlueprint(blueprintId: string, data: Partial<IntentBlueprint>) {
  return http.put<IntentBlueprint>(`/v1/intent/blueprint/${blueprintId}`, data)
}

/** 锁定蓝图 */
export function lockBlueprint(blueprintId: string) {
  return http.post(`/v1/intent/blueprint/${blueprintId}/lock`)
}

/** 获取蓝图列表 */
export function getBlueprints(params?: { page?: number; page_size?: number }) {
  return http.get<{ items: IntentBlueprint[]; total: number }>('/v1/intent/blueprints', { params })
}

/** 提交追问答案 */
export function submitQuestionAnswer(blueprintId: string, questionId: string, answer: string) {
  return http.post(`/v1/intent/blueprint/${blueprintId}/questions`, { question_id: questionId, answer })
}

/** 跳过追问 */
export function skipQuestion(questionId: string) {
  return http.post(`/v1/intent/question/${questionId}/skip`)
}

/** 获取跳过率 */
export function getSkipRate(blueprintId: string) {
  return http.get<{ skip_rate: number }>(`/v1/intent/blueprint/${blueprintId}/skip-rate`)
}
