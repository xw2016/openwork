// OpenWork 平台 TypeScript 类型定义
// 与后端 SQLAlchemy 模型对齐

/** 用户角色 */
export type UserRole = 'employer' | 'freelancer' | 'admin'

/** 用户状态 */
export type UserStatus = 'active' | 'disabled' | 'pending'

/** 用户信息 */
export interface User {
  id: string
  user_type: UserRole
  nickname: string
  avatar: string | null
  avatar_url: string | null
  phone: string | null
  email: string | null
  bio: string | null
  credit_score: number
  completed_tasks: number
  total_tasks: number
  status: UserStatus
  created_at: string
  updated_at: string
}

/** 登录请求 */
export interface LoginRequest {
  phone?: string
  email?: string
  password: string
}

/** 注册请求 */
export interface RegisterRequest {
  phone?: string
  email?: string
  password: string
  nickname: string
  user_type: UserRole
}

/** 登录响应 */
export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/** 合约状态 — 与后端 ContractStatus 枚举对齐 */
export type ContractStatus =
  | 'draft'           // 草稿
  | 'pending'         // 待接单
  | 'in_progress'     // 进行中
  | 'review'          // 验收中
  | 'completed'       // 已完成
  | 'terminated'      // 已终止
  | 'disputed'        // 争议中

/** 任务类型 */
export type TaskType =
  | 'development'
  | 'design'
  | 'copywriting'
  | 'translation'
  | 'data_labeling'
  | 'consulting'
  | 'other'

/** 合约（任务）— 与后端 Contract 模型对齐 */
export interface Contract {
  id: string
  contract_no: string
  employer_id: string
  freelancer_id: string | null
  title: string
  task_type: TaskType
  base_amount: number
  bonus_amount: number
  deliverables: Record<string, unknown>
  status: ContractStatus
  version: number
  deadline: string | null
  created_at: string
  updated_at: string
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

/** 交易类型 — 与后端 TransactionType 对齐 */
export type TransactionType = 'escrow' | 'payment' | 'refund' | 'bonus'

/** 交易状态 — 与后端 TransactionStatus 对齐 */
export type TransactionStatus = 'pending' | 'completed' | 'failed' | 'cancelled'

/** 交易记录 — 与后端 Transaction 模型对齐 */
export interface Transaction {
  id: string
  contract_id: string
  transaction_type: TransactionType
  amount: number
  from_user_id: string | null
  to_user_id: string | null
  commission: number
  status: TransactionStatus
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
