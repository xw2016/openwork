// OpenWork 平台 TypeScript 类型定义

/** 用户角色 */
export type UserRole = 'employer' | 'freelancer'

/** 用户信息 */
export interface User {
  id: string
  username: string
  email: string
  role: UserRole
  credit_score: number
  created_at: string
}

/** 登录请求 */
export interface LoginRequest {
  username: string
  password: string
}

/** 注册请求 */
export interface RegisterRequest {
  username: string
  email: string
  password: string
  role: UserRole
}

/** 登录响应 */
export interface LoginResponse {
  access_token: string
  token_type: string
}

/** 合约状态 */
export type ContractStatus =
  | 'draft'           // 草稿
  | 'pending_accept'  // 待接单
  | 'in_progress'     // 进行中
  | 'submitted'       // 已提交交付物
  | 'reviewing'       // AI验收中
  | 'completed'       // 已完成
  | 'disputed'        // 争议中
  | 'cancelled'       // 已取消

/** 合约（任务） */
export interface Contract {
  id: string
  title: string
  description: string
  employer_id: string
  freelancer_id: string | null
  budget: number
  status: ContractStatus
  intent_model: string       // AI生成的意图模型
  acceptance_criteria: string // 验收标准
  created_at: string
  updated_at: string
  deadline: string | null
}

/** 交付物 */
export interface Deliverable {
  id: string
  contract_id: string
  freelancer_id: string
  file_url: string
  file_name: string
  description: string
  submitted_at: string
}

/** AI验收记录 */
export interface AcceptanceRecord {
  id: string
  contract_id: string
  deliverable_id: string
  score: number             // 0-100
  passed: boolean
  report: string            // AI验收报告
  details: AcceptanceDetail[]
  created_at: string
}

/** 验收详情项 */
export interface AcceptanceDetail {
  criterion: string   // 验收标准项
  passed: boolean
  score: number
  comment: string
}

/** 交易记录 */
export interface Transaction {
  id: string
  contract_id: string
  from_user_id: string
  to_user_id: string
  amount: number
  type: 'payment' | 'refund' | 'penalty'
  status: 'pending' | 'completed' | 'failed'
  created_at: string
}

/** 信用记录 */
export interface CreditRecord {
  id: string
  user_id: string
  change: number           // 信用分变动
  reason: string
  contract_id: string | null
  created_at: string
}

/** 分页响应 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** API 错误响应 */
export interface ApiError {
  detail: string
  status_code: number
}
