# 可信任务市场（OpenWork）— 项目开发计划 V1.0

> 基于《可信任务市场 产品设计文档 V1.0》制定
> 生成日期：2026-05-24

---

## 一、技术栈选型

| 层级 | 技术方案 | 说明 |
|:---|:---|:---|
| **前端** | Vue 3 + TypeScript + Naive UI | 响应式设计，支持PC和移动端 |
| **后端** | Python FastAPI | 高性能异步框架，便于AI集成 |
| **数据库** | PostgreSQL | JSON字段支持良好，适合存储意图蓝图等结构化数据 |
| **缓存** | Redis | 会话管理、任务状态缓存 |
| **AI服务** | LLM API（大模型对话 + 文档解析） | 意图建模、验收检查 |
| **文件存储** | MinIO / 阿里云OSS | 交付物加密存储 |
| **区块链** | 蚂蚁链/腾讯云区块链（联盟链） | MVP阶段关键节点哈希上链 |
| **支付** | 微信支付/支付宝（托管模式） | 资金托管与自动结算 |
| **认证** | JWT Token + 刷新机制 | 用户身份认证 |
| **部署** | Docker + Docker Compose | 容器化部署 |

---

## 二、开发阶段划分

### 阶段一：项目基础搭建（第1-2周）

| 序号 | 工作项 | 说明 | 负责Agent |
|:---|:---|:---|:---|
| 1.1 | 技术架构设计 | 整体架构、服务拆分、技术选型确认 | `engineering-software-architect` |
| 1.2 | 数据库Schema设计 | 基于设计文档第7章，设计完整的数据库表结构和索引 | `engineering-database-optimizer` |
| 1.3 | API接口规范定义 | 基于设计文档第8章，输出OpenAPI/Swagger规范 | `engineering-backend-architect` |
| 1.4 | 前端工程搭建 | Vue3 + Vite + Naive UI + 路由 + 状态管理 | `engineering-frontend-developer` |
| 1.5 | 后端工程搭建 | FastAPI项目结构、数据库ORM、中间件、认证框架 | `engineering-backend-architect` |
| 1.6 | CI/CD流水线 | Docker构建、自动化测试、部署脚本 | `engineering-devops-automator` |
| 1.7 | 安全基线 | HTTPS、JWT、CORS、SQL注入防护、接口限流 | `engineering-security-engineer` |

---

### 阶段二：核心后端模块开发（第3-6周）

| 序号 | 工作项 | 说明 | 负责Agent |
|:---|:---|:---|:---|
| **M1：用户与认证模块** | | | |
| 2.1 | 用户注册/登录 | 手机号+验证码、邮箱注册、JWT认证 | `engineering-backend-architect` |
| 2.2 | 角色权限系统 | RBAC：雇主/自由职业者/管理员三角色权限矩阵 | `engineering-backend-architect` |
| 2.3 | 用户资料管理 | 头像、昵称、领域标签、实名认证（加密存储） | `engineering-backend-architect` |
| **M2：AI意图建模模块** | | | |
| 2.4 | 2C1H意图建模引擎 | 多轮对话、追问策略、意图蓝图生成 | `engineering-ai-engineer` |
| 2.5 | 意图蓝图CRUD | 蓝图创建、修改、锁定、版本管理 | `engineering-backend-architect` |
| 2.6 | AI追问分级处理 | 跳过机制、待澄清标记、30%跳过率校验 | `engineering-ai-engineer` |
| **M3：任务合约与发布模块** | | | |
| 2.7 | 合约生命周期管理 | 草稿→已发布→已接单→执行中→待验收→已完成 全状态流转 | `engineering-backend-architect` |
| 2.8 | 交付物清单生成 | AI根据任务类型自动拆解交付物（含格式、数量、验收标准） | `engineering-ai-engineer` |
| 2.9 | 结算方式配置 | 基础报酬 / 基础+效果奖金，佣金计算 | `engineering-backend-architect` |
| **M4：任务市场与接单模块** | | | |
| 2.10 | 任务市场列表 | 多维筛选（状态/类型/领域/预算）、排序、分页 | `engineering-backend-architect` |
| 2.11 | 接单流程 | 确认接单、合约状态变更、通知雇主 | `engineering-backend-architect` |
| 2.12 | 交付物上传 | 文件上传（加密存储）、版本管理、提交验收 | `engineering-backend-architect` |
| **M5：AI验收模块** | | | |
| 2.13 | 验收引擎核心 | 逐项检查：格式/规模/内容要素/引用/完整性 | `engineering-ai-engineer` |
| 2.14 | 验收报告生成 | 结构化报告（总览+逐项结果+不通过说明） | `engineering-ai-engineer` |
| 2.15 | 修改与重提机制 | 3次修改上限、超限人工审核、误判处理 | `engineering-backend-architect` |
| **M6：资金托管与结算模块** | | | |
| 2.16 | 资金托管流程 | 雇主预付→冻结→验收通过→释放 全链路 | `engineering-backend-architect` |
| 2.17 | 自动结算 | 验收通过后1分钟内释放、佣金扣除 | `engineering-backend-architect` |
| 2.18 | 退款与终止 | 过期退款、取消退款、超限部分结算 | `engineering-backend-architect` |
| **M7：信用记录模块** | | | |
| 2.19 | 雇主信用分计算 | 完成率×40 + 结算效率×30 + 拒付扣分×30 | `engineering-backend-architect` |
| 2.20 | 自由职业者信用分 | 一次通过率×35 + 延迟×25 + 完成率×25 + 评分×15 | `engineering-backend-architect` |
| 2.21 | 冷启动策略 | 新用户默认70分、前5任务标注"新用户"、收敛机制 | `engineering-backend-architect` |
| **M8：链上存证模块** | | | |
| 2.22 | 存证服务封装 | 7个存证节点的统一上链接口 | `engineering-backend-architect` |
| 2.23 | 哈希计算与验证 | SHA-256哈希、链上查询、哈希验证工具 | `engineering-backend-architect` |
| 2.24 | 隐私分层 | 公开层（链上）/授权层（加密云存储）/私密层（内部DB） | `engineering-security-engineer` |

---

### 阶段三：前端页面开发（第5-8周，与后端并行）

| 序号 | 页面 | 说明 | 负责Agent |
|:---|:---|:---|:---|
| 3.1 | P1 雇主首页 | 任务列表+搜索+状态Tab+发布入口 | `engineering-frontend-developer` |
| 3.2 | P2 AI意图建模页 | 对话式交互+多轮追问+蓝图预览确认 | `engineering-frontend-developer` |
| 3.3 | P3 交付物与验收确认页 | 交付清单展示+阈值调整+结算方式选择 | `engineering-frontend-developer` |
| 3.4 | P4 支付确认页 | 金额明细+托管说明+支付按钮 | `engineering-frontend-developer` |
| 3.5 | P5 任务市场页 | 任务卡片列表+筛选器+接单入口 | `engineering-frontend-developer` |
| 3.6 | P6 任务详情页 | 意图蓝图+交付清单+结算信息+雇主信息 | `engineering-frontend-developer` |
| 3.7 | P7 交付物上传页 | 文件上传+进度+提交验收 | `engineering-frontend-developer` |
| 3.8 | P8/P9 AI验收报告页 | 双视角（雇主/自由职业者）验收结果展示 | `engineering-frontend-developer` |
| 3.9 | P10 信用记录页 | 信用分展示+明细+历史任务+链上存证 | `engineering-frontend-developer` |
| 3.10 | 移动端适配 | 响应式布局，确保iOS/Android浏览器兼容 | `engineering-frontend-developer` |

---

### 阶段四：集成测试与安全审计（第9-10周）

| 序号 | 工作项 | 说明 | 负责Agent |
|:---|:---|:---|:---|
| 4.1 | API接口测试 | 全部接口的功能测试、边界测试、异常测试 | `testing-api-tester` |
| 4.2 | AI验收准确率测试 | 构造测试用例集，验证误判率≤5% | `engineering-ai-engineer` |
| 4.3 | 资金流测试 | 托管→释放→退款全链路资金一致性验证 | `testing-api-tester` |
| 4.4 | 安全审计 | SQL注入、XSS、CSRF、认证绕过、敏感数据泄露 | `engineering-security-engineer` |
| 4.5 | 性能测试 | 页面加载≤2s、AI响应≤3s、验收≤3min | `testing-performance-benchmarker` |
| 4.6 | 代码审查 | 全量代码Review，聚焦正确性、可维护性、安全性 | `engineering-code-reviewer` |

---

### 阶段五：部署上线（第11-12周）

| 序号 | 工作项 | 说明 | 负责Agent |
|:---|:---|:---|:---|
| 5.1 | 生产环境搭建 | 服务器、数据库、Redis、OSS、域名、SSL | `engineering-devops-automator` |
| 5.2 | Docker化部署 | Dockerfile + docker-compose + 环境变量管理 | `engineering-devops-automator` |
| 5.3 | 监控与日志 | 应用监控、错误告警、日志收集 | `engineering-sre` |
| 5.4 | 文档输出 | API文档、部署文档、运维手册 | `engineering-technical-writer` |

---

## 三、Agent角色总览

| Agent角色 | 负责工作 |
|:---|:---|
| `engineering-software-architect` | 整体技术架构设计、服务拆分、技术选型 |
| `engineering-backend-architect` | 后端核心业务开发（用户/合约/市场/资金/信用） |
| `engineering-ai-engineer` | AI引擎开发（意图建模、验收引擎、文档解析） |
| `engineering-frontend-developer` | 全部前端页面开发（10个页面+移动端适配） |
| `engineering-database-optimizer` | 数据库Schema设计、索引优化、查询调优 |
| `engineering-security-engineer` | 安全基线、加密方案、安全审计 |
| `engineering-devops-automator` | CI/CD、Docker化、环境搭建、部署自动化 |
| `engineering-sre` | 生产监控、告警、日志、可用性保障 |
| `engineering-technical-writer` | API文档、部署文档、运维手册 |
| `testing-api-tester` | 接口测试、资金流测试 |
| `testing-performance-benchmarker` | 性能测试、压力测试 |
| `engineering-code-reviewer` | 全量代码审查 |

---

## 四、里程碑与交付物

| 里程碑 | 时间 | 交付物 |
|:---|:---|:---|
| M0 项目启动 | 第2周末 | 技术架构文档、DB Schema、API规范、开发环境就绪 |
| M1 后端核心完成 | 第6周末 | 6大模块API全部可用，单元测试覆盖率≥80% |
| M2 前端完成 | 第8周末 | 10个页面全部完成，前后端联调通过 |
| M3 测试通过 | 第10周末 | 全量测试通过，安全审计报告，性能达标 |
| M4 正式上线 | 第12周末 | 生产环境部署，监控就绪，文档齐全 |

---

## 五、风险与依赖

| 风险项 | 影响 | 缓解措施 |
|:---|:---|:---|
| AI验收准确率不足 | 误判率>5%导致用户信任下降 | MVP阶段人工复核兜底，持续优化Prompt |
| 支付通道接入延迟 | 影响资金托管功能 | 提前申请支付资质，备选方案 |
| 区块链服务稳定性 | 存证延迟>30s | 联盟链SLA保障，异步重试机制 |
| LLM API成本 | 大量对话和验收消耗token | 缓存策略、模型选型优化 |
