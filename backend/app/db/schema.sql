-- ============================================================
-- OpenWork Platform - PostgreSQL Database Schema
-- Based on Product Design Document Chapter 7
-- ============================================================
-- Version: 1.0.0
-- Created: 2026-05-24
-- Database: PostgreSQL 15+
-- ============================================================

-- 启用 UUID 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. 枚举类型定义 (ENUM Types)
-- ============================================================

-- 用户类型：雇主、自由职业者、管理员
CREATE TYPE user_type_enum AS ENUM ('employer', 'freelancer', 'admin');

-- 用户状态：正常、禁用、待审核
CREATE TYPE user_status_enum AS ENUM ('active', 'disabled', 'pending');

-- 任务类型：开发、设计、文案、翻译、数据标注等
CREATE TYPE task_type_enum AS ENUM (
    'development',   -- 软件开发
    'design',        -- 设计
    'copywriting',   -- 文案
    'translation',   -- 翻译
    'data_labeling', -- 数据标注
    'consulting',    -- 咨询
    'other'          -- 其他
);

-- 合约状态：草稿、待确认、进行中、待验收、已完成、已终止、争议中
CREATE TYPE contract_status_enum AS ENUM (
    'draft',         -- 草稿
    'pending',       -- 待确认
    'in_progress',   -- 进行中
    'review',        -- 待验收
    'completed',     -- 已完成
    'terminated',    -- 已终止
    'disputed'       -- 争议中
);

-- 交付物验收状态：待提交、待验收、已通过、已拒绝
CREATE TYPE acceptance_status_enum AS ENUM (
    'not_submitted', -- 待提交
    'pending',       -- 待验收
    'approved',      -- 已通过
    'rejected'       -- 已拒绝
);

-- 验收结果：通过、拒绝
CREATE TYPE acceptance_result_enum AS ENUM ('approved', 'rejected');

-- 交易类型：托管、支付、退款、奖励
CREATE TYPE transaction_type_enum AS ENUM (
    'escrow',    -- 托管
    'payment',   -- 支付
    'refund',    -- 退款
    'bonus'      -- 奖励
);

-- 交易状态：待处理、已完成、已失败、已取消
CREATE TYPE transaction_status_enum AS ENUM (
    'pending',   -- 待处理
    'completed', -- 已完成
    'failed',    -- 已失败
    'cancelled'  -- 已取消
);

-- 链上存证节点类型：合约创建、交付提交、验收确认、交易完成、争议发起
CREATE TYPE node_type_enum AS ENUM (
    'contract_created',   -- 合约创建
    'deliverable_submit', -- 交付提交
    'acceptance_confirm', -- 验收确认
    'transaction_complete', -- 交易完成
    'dispute_initiated'   -- 争议发起
);

-- ============================================================
-- 2. 用户表 (users)
-- ============================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_type       user_type_enum NOT NULL DEFAULT 'freelancer',
    nickname        VARCHAR(50) NOT NULL,
    avatar          VARCHAR(500),                     -- 头像URL
    phone           VARCHAR(20) UNIQUE NOT NULL,      -- 手机号（唯一）
    email           VARCHAR(100) UNIQUE,              -- 邮箱（唯一）
    real_name       VARCHAR(255),                     -- 真实姓名（AES加密存储）
    id_card         VARCHAR(255),                     -- 身份证号（AES加密存储）
    credit_score    INTEGER NOT NULL DEFAULT 600,     -- 信用分，默认600
    -- credit_detail: 信用评分明细JSON
    -- 结构: {"history": [...], "deductions": [...], "bonuses": [...]}
    credit_detail   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          user_status_enum NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- users 表注释
COMMENT ON TABLE users IS '用户表 - 存储平台所有用户信息';
COMMENT ON COLUMN users.id IS '用户唯一标识（UUID）';
COMMENT ON COLUMN users.user_type IS '用户类型：employer-雇主, freelancer-自由职业者, admin-管理员';
COMMENT ON COLUMN users.nickname IS '用户昵称';
COMMENT ON COLUMN users.avatar IS '头像URL地址';
COMMENT ON COLUMN users.phone IS '手机号码（用于登录和验证）';
COMMENT ON COLUMN users.email IS '电子邮箱';
COMMENT ON COLUMN users.real_name IS '真实姓名（AES加密存储，解密后为明文）';
COMMENT ON COLUMN users.id_card IS '身份证号码（AES加密存储，解密后为明文）';
COMMENT ON COLUMN users.credit_score IS '信用评分，范围0-1000，默认600';
COMMENT ON COLUMN users.credit_detail IS '信用评分明细，JSON格式：{"history": [], "deductions": [], "bonuses": []}';
COMMENT ON COLUMN users.status IS '用户状态：active-正常, disabled-禁用, pending-待审核';

-- ============================================================
-- 3. 任务合约表 (contracts)
-- ============================================================

CREATE TABLE contracts (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_no       VARCHAR(50) UNIQUE NOT NULL,       -- 合约编号，格式: OW-YYYYMMDD-XXXXX
    employer_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    freelancer_id     UUID REFERENCES users(id) ON DELETE RESTRICT,
    title             VARCHAR(200) NOT NULL,              -- 任务标题
    task_type         task_type_enum NOT NULL,            -- 任务类型
    -- intent_blueprint: 意图蓝图JSON，描述任务意图与目标
    -- 结构: {"objective": "", "requirements": [], "constraints": [], "evaluation_metrics": []}
    intent_blueprint  JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- deliverables: 预期交付物列表JSON
    -- 结构: [{"index": 1, "name": "", "description": "", "format": ""}]
    deliverables      JSONB NOT NULL DEFAULT '[]'::jsonb,
    base_amount       DECIMAL(12, 2) NOT NULL DEFAULT 0.00, -- 基础金额（元）
    bonus_amount      DECIMAL(12, 2) NOT NULL DEFAULT 0.00, -- 奖金金额（元）
    -- bonus_condition: 奖金触发条件JSON
    -- 结构: {"type": "early_delivery|quality_score", "threshold": 0, "description": ""}
    bonus_condition   JSONB DEFAULT NULL,
    tracking_period   INTEGER,                            -- 跟踪期（天）
    commission_rate   DECIMAL(5, 4) NOT NULL DEFAULT 0.0500, -- 平台佣金比例，默认5%
    deadline          TIMESTAMPTZ,                        -- 截止时间
    version           INTEGER NOT NULL DEFAULT 1,        -- 版本号
    status            contract_status_enum NOT NULL DEFAULT 'draft',
    block_hash        VARCHAR(128),                       -- 区块链哈希（合约创建时上链）
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- contracts 表注释
COMMENT ON TABLE contracts IS '任务合约表 - 存储雇主与自由职业者之间的任务合约';
COMMENT ON COLUMN contracts.id IS '合约唯一标识（UUID）';
COMMENT ON COLUMN contracts.contract_no IS '合约编号，自动生成，格式: OW-YYYYMMDD-XXXXX';
COMMENT ON COLUMN contracts.employer_id IS '雇主用户ID（外键 -> users.id）';
COMMENT ON COLUMN contracts.freelancer_id IS '自由职业者用户ID（外键 -> users.id），竞标后确定';
COMMENT ON COLUMN contracts.title IS '任务标题';
COMMENT ON COLUMN contracts.task_type IS '任务类型枚举';
COMMENT ON COLUMN contracts.intent_blueprint IS '意图蓝图，JSON格式：{"objective": "", "requirements": [], "constraints": [], "evaluation_metrics": []}';
COMMENT ON COLUMN contracts.deliverables IS '预期交付物列表，JSON数组格式：[{"index": 1, "name": "", "description": "", "format": ""}]';
COMMENT ON COLUMN contracts.base_amount IS '基础金额（人民币元），精度到分';
COMMENT ON COLUMN contracts.bonus_amount IS '奖金金额（人民币元）';
COMMENT ON COLUMN contracts.bonus_condition IS '奖金触发条件，JSON格式：{"type": "early_delivery|quality_score", "threshold": 0}';
COMMENT ON COLUMN contracts.tracking_period IS '跟踪期（天），任务完成后的跟踪验证天数';
COMMENT ON COLUMN contracts.commission_rate IS '平台佣金比例，默认0.0500（5%）';
COMMENT ON COLUMN contracts.deadline IS '任务截止时间';
COMMENT ON COLUMN contracts.version IS '合约版本号，每次修改递增';
COMMENT ON COLUMN contracts.status IS '合约状态枚举';
COMMENT ON COLUMN contracts.block_hash IS '区块链存证哈希';

-- ============================================================
-- 4. 交付物表 (deliverables)
-- ============================================================

CREATE TABLE deliverables (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id         UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    deliverable_index   INTEGER NOT NULL DEFAULT 1,       -- 交付物序号
    name                VARCHAR(200) NOT NULL,             -- 交付物名称
    required_format     VARCHAR(100),                      -- 要求格式
    -- acceptance_criteria: 验收标准JSON
    -- 结构: {"criteria": [{"name": "", "weight": 0, "pass_threshold": 0}], "auto_check_rules": []}
    acceptance_criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
    file_url            VARCHAR(500),                      -- 文件存储URL
    file_hash           VARCHAR(128),                      -- 文件内容SHA-256哈希
    submit_version      INTEGER NOT NULL DEFAULT 1,       -- 提交版本号
    submit_time         TIMESTAMPTZ,                       -- 提交时间
    -- acceptance_result: 验收结果JSON
    -- 结构: {"scores": [], "overall_score": 0, "comments": "", "auto_check_results": []}
    acceptance_result   JSONB DEFAULT NULL,
    acceptance_status   acceptance_status_enum NOT NULL DEFAULT 'not_submitted',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (contract_id, deliverable_index, submit_version)
);

-- deliverables 表注释
COMMENT ON TABLE deliverables IS '交付物表 - 存储任务合约的交付物信息';
COMMENT ON COLUMN deliverables.id IS '交付物唯一标识（UUID）';
COMMENT ON COLUMN deliverables.contract_id IS '所属合约ID（外键 -> contracts.id）';
COMMENT ON COLUMN deliverables.deliverable_index IS '交付物序号，同一合约内唯一';
COMMENT ON COLUMN deliverables.name IS '交付物名称';
COMMENT ON COLUMN deliverables.required_format IS '要求格式，如 pdf, zip, github_url';
COMMENT ON COLUMN deliverables.acceptance_criteria IS '验收标准，JSON格式：{"criteria": [{"name": "", "weight": 0, "pass_threshold": 0}], "auto_check_rules": []}';
COMMENT ON COLUMN deliverables.file_url IS '文件存储URL（OSS或本地路径）';
COMMENT ON COLUMN deliverables.file_hash IS '文件SHA-256哈希值';
COMMENT ON COLUMN deliverables.submit_version IS '提交版本号，重新提交时递增';
COMMENT ON COLUMN deliverables.submit_time IS '提交时间';
COMMENT ON COLUMN deliverables.acceptance_result IS '验收结果，JSON格式：{"scores": [], "overall_score": 0, "comments": "", "auto_check_results": []}';
COMMENT ON COLUMN deliverables.acceptance_status IS '验收状态枚举';

-- ============================================================
-- 5. 验收记录表 (acceptance_records)
-- ============================================================

CREATE TABLE acceptance_records (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id           UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    submit_version        INTEGER NOT NULL,                  -- 对应的提交版本
    -- acceptance_report: 验收报告JSON
    -- 结构: {
    --   "evaluator_id": "",
    --   "deliverable_results": [{"deliverable_id": "", "score": 0, "passed": true, "comments": ""}],
    --   "overall_score": 0,
    --   "summary": "",
    --   "auto_check_summary": {}
    -- }
    acceptance_report     JSONB NOT NULL DEFAULT '{}'::jsonb,
    result                acceptance_result_enum NOT NULL,   -- 验收结果
    settlement_triggered  BOOLEAN NOT NULL DEFAULT FALSE,    -- 是否触发结算
    block_hash            VARCHAR(128),                      -- 区块链存证哈希
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- acceptance_records 表注释
COMMENT ON TABLE acceptance_records IS '验收记录表 - 存储每次验收的详细记录';
COMMENT ON COLUMN acceptance_records.id IS '验收记录唯一标识（UUID）';
COMMENT ON COLUMN acceptance_records.contract_id IS '所属合约ID（外键 -> contracts.id）';
COMMENT ON COLUMN acceptance_records.submit_version IS '对应交付物的提交版本号';
COMMENT ON COLUMN acceptance_records.acceptance_report IS '验收报告，JSON格式：{"evaluator_id": "", "deliverable_results": [], "overall_score": 0, "summary": "", "auto_check_summary": {}}';
COMMENT ON COLUMN acceptance_records.result IS '验收结果：approved-通过, rejected-拒绝';
COMMENT ON COLUMN acceptance_records.settlement_triggered IS '是否触发资金结算';
COMMENT ON COLUMN acceptance_records.block_hash IS '验收确认的区块链存证哈希';

-- ============================================================
-- 6. 交易记录表 (transactions)
-- ============================================================

CREATE TABLE transactions (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id       UUID NOT NULL REFERENCES contracts(id) ON DELETE RESTRICT,
    transaction_type  transaction_type_enum NOT NULL,       -- 交易类型
    amount            DECIMAL(12, 2) NOT NULL,              -- 交易金额（元）
    from_user_id      UUID REFERENCES users(id) ON DELETE RESTRICT,  -- 付款方
    to_user_id        UUID REFERENCES users(id) ON DELETE RESTRICT,  -- 收款方
    commission        DECIMAL(12, 2) NOT NULL DEFAULT 0.00, -- 平台佣金（元）
    status            transaction_status_enum NOT NULL DEFAULT 'pending',
    block_hash        VARCHAR(128),                         -- 区块链存证哈希
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- transactions 表注释
COMMENT ON TABLE transactions IS '交易记录表 - 存储平台所有资金流转记录';
COMMENT ON COLUMN transactions.id IS '交易记录唯一标识（UUID）';
COMMENT ON COLUMN transactions.contract_id IS '关联合约ID（外键 -> contracts.id）';
COMMENT ON COLUMN transactions.transaction_type IS '交易类型：escrow-托管, payment-支付, refund-退款, bonus-奖励';
COMMENT ON COLUMN transactions.amount IS '交易金额（人民币元），精度到分';
COMMENT ON COLUMN transactions.from_user_id IS '付款方用户ID（外键 -> users.id），托管时为雇主';
COMMENT ON COLUMN transactions.to_user_id IS '收款方用户ID（外键 -> users.id），支付时为自由职业者';
COMMENT ON COLUMN transactions.commission IS '平台佣金金额（人民币元）';
COMMENT ON COLUMN transactions.status IS '交易状态：pending-待处理, completed-已完成, failed-已失败, cancelled-已取消';
COMMENT ON COLUMN transactions.block_hash IS '交易上链的区块链存证哈希';

-- ============================================================
-- 7. 链上存证表 (blockchain_records)
-- ============================================================

CREATE TABLE blockchain_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id     UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    node_type       node_type_enum NOT NULL,                -- 存证节点类型
    content_hash    VARCHAR(128) NOT NULL,                   -- 内容哈希（SHA-256）
    block_hash      VARCHAR(128) NOT NULL,                   -- 区块链哈希
    block_height    BIGINT,                                  -- 区块高度
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()       -- 上链时间
);

-- blockchain_records 表注释
COMMENT ON TABLE blockchain_records IS '链上存证表 - 记录关键操作的区块链存证信息';
COMMENT ON COLUMN blockchain_records.id IS '存证记录唯一标识（UUID）';
COMMENT ON COLUMN blockchain_records.contract_id IS '关联合约ID（外键 -> contracts.id）';
COMMENT ON COLUMN blockchain_records.node_type IS '存证节点类型：contract_created-合约创建, deliverable_submit-交付提交, acceptance_confirm-验收确认, transaction_complete-交易完成, dispute_initiated-争议发起';
COMMENT ON COLUMN blockchain_records.content_hash IS '被存证内容的SHA-256哈希';
COMMENT ON COLUMN blockchain_records.block_hash IS '区块链上的区块哈希';
COMMENT ON COLUMN blockchain_records.block_height IS '区块高度（区块序号）';
COMMENT ON COLUMN blockchain_records.timestamp IS '上链时间戳';

-- ============================================================
-- 8. 索引设计 (Indexes)
-- ============================================================

-- === users 表索引 ===
-- 手机号查询（登录、注册验证）
CREATE INDEX idx_users_phone ON users(phone);
-- 邮箱查询（登录、通知）
CREATE INDEX idx_users_email ON users(email);
-- 按用户类型筛选
CREATE INDEX idx_users_user_type ON users(user_type);
-- 用户状态筛选
CREATE INDEX idx_users_status ON users(status);
-- 创建时间排序
CREATE INDEX idx_users_created_at ON users(created_at DESC);

-- === contracts 表索引 ===
-- 雇主合约列表查询
CREATE INDEX idx_contracts_employer_id ON contracts(employer_id);
-- 自由职业者合约列表查询
CREATE INDEX idx_contracts_freelancer_id ON contracts(freelancer_id);
-- 按合约状态筛选
CREATE INDEX idx_contracts_status ON contracts(status);
-- 按创建时间排序（合约列表分页）
CREATE INDEX idx_contracts_created_at ON contracts(created_at DESC);
-- 合约编号查询
CREATE INDEX idx_contracts_contract_no ON contracts(contract_no);
-- 复合索引：雇主+状态（雇主看自己的合约列表）
CREATE INDEX idx_contracts_employer_status ON contracts(employer_id, status);
-- 复合索引：自由职业者+状态（自由职业者看自己的合约列表）
CREATE INDEX idx_contracts_freelancer_status ON contracts(freelancer_id, status);
-- 截止时间查询（即将到期的合约）
CREATE INDEX idx_contracts_deadline ON contracts(deadline) WHERE deadline IS NOT NULL;

-- === deliverables 表索引 ===
-- 按合约查询交付物
CREATE INDEX idx_deliverables_contract_id ON deliverables(contract_id);
-- 按验收状态筛选
CREATE INDEX idx_deliverables_acceptance_status ON deliverables(acceptance_status);
-- 复合索引：合约+验收状态（查询某合约待验收的交付物）
CREATE INDEX idx_deliverables_contract_status ON deliverables(contract_id, acceptance_status);

-- === acceptance_records 表索引 ===
-- 按合约查询验收记录
CREATE INDEX idx_acceptance_records_contract_id ON acceptance_records(contract_id);
-- 按创建时间排序
CREATE INDEX idx_acceptance_records_created_at ON acceptance_records(created_at DESC);

-- === transactions 表索引 ===
-- 按合约查询交易记录
CREATE INDEX idx_transactions_contract_id ON transactions(contract_id);
-- 按付款方查询
CREATE INDEX idx_transactions_from_user_id ON transactions(from_user_id);
-- 按收款方查询
CREATE INDEX idx_transactions_to_user_id ON transactions(to_user_id);
-- 按创建时间排序（账单分页）
CREATE INDEX idx_transactions_created_at ON transactions(created_at DESC);
-- 复合索引：用户交易记录查询（付款+收款）
CREATE INDEX idx_transactions_from_created ON transactions(from_user_id, created_at DESC);
CREATE INDEX idx_transactions_to_created ON transactions(to_user_id, created_at DESC);
-- 交易状态筛选
CREATE INDEX idx_transactions_status ON transactions(status);

-- === blockchain_records 表索引 ===
-- 按合约查询存证
CREATE INDEX idx_blockchain_records_contract_id ON blockchain_records(contract_id);
-- 按存证类型筛选
CREATE INDEX idx_blockchain_records_node_type ON blockchain_records(node_type);
-- 复合索引：合约+类型
CREATE INDEX idx_blockchain_records_contract_type ON blockchain_records(contract_id, node_type);
-- 区块链哈希查询（链上验证）
CREATE INDEX idx_blockchain_records_block_hash ON blockchain_records(block_hash);

-- ============================================================
-- 9. 自动更新 updated_at 触发器
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为有 updated_at 字段的表创建触发器
CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_contracts_updated_at
    BEFORE UPDATE ON contracts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_deliverables_updated_at
    BEFORE UPDATE ON deliverables
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 10. 初始化数据 (Seed Data)
-- ============================================================

-- 管理员用户（密码哈希需在应用层生成，这里使用占位符）
INSERT INTO users (id, user_type, nickname, phone, email, real_name, credit_score, status) VALUES
    ('00000000-0000-0000-0000-000000000001', 'admin', '系统管理员', '13800000000', 'admin@openwork.com', '管理员', 1000, 'active');

-- 平台配置表（可选，用于存储平台级配置）
CREATE TABLE IF NOT EXISTS platform_config (
    config_key    VARCHAR(100) PRIMARY KEY,
    config_value  JSONB NOT NULL,
    description   VARCHAR(500),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE platform_config IS '平台配置表 - 存储全局配置参数';

CREATE TRIGGER trigger_platform_config_updated_at
    BEFORE UPDATE ON platform_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 基础配置数据
INSERT INTO platform_config (config_key, config_value, description) VALUES
    ('commission_rate', '{"default": 0.05, "min": 0.01, "max": 0.15}', '平台佣金比例配置，默认5%，范围1%-15%'),
    ('credit_score', '{"default": 600, "min": 0, "max": 1000, "dispute_penalty": -50}', '信用评分配置'),
    ('tracking_period', '{"default_days": 7, "max_days": 90}', '跟踪期配置（天）'),
    ('escrow_timeout', '{"auto_release_days": 30}', '托管超时自动释放天数'),
    ('version', '{"schema": "1.0.0"}', '数据库Schema版本');

-- ============================================================
-- Schema 创建完成
-- ============================================================
