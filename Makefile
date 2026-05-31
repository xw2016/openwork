# ============================================================
# OpenWork Makefile
# 常用开发/部署命令集合
# ============================================================

# 默认 Shell
SHELL := /bin/bash

# 项目路径
PROJECT_ROOT := $(shell pwd)
BACKEND_DIR  := $(PROJECT_ROOT)/backend
FRONTEND_DIR := $(PROJECT_ROOT)/frontend

# Docker Compose 命令
DC      := docker compose
DC_DEV  := $(DC) -f docker-compose.yml -f docker-compose.dev.yml

# 颜色输出
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
NC     := \033[0m

.PHONY: help dev dev-down build up down logs test lint \
        db-migrate db-upgrade db-reset \
        setup install clean \
        deploy health

# ---- 默认目标 ----
help: ## 显示帮助信息
	@echo ""
	@echo "OpenWork 可信任务市场 — 可用命令："
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-16s$(NC) %s\n", $$1, $$2}'
	@echo ""

# ============================================================
# 开发环境
# ============================================================

setup: ## 一键搭建开发环境（检查依赖、创建 venv、安装依赖）
	@echo -e "$(GREEN)[1/4] 检查系统依赖...$(NC)"
	@command -v python3 >/dev/null 2>&1 || { echo -e "$(RED)错误: 未找到 python3$(NC)"; exit 1; }
	@command -v node >/dev/null 2>&1 || { echo -e "$(RED)错误: 未找到 node$(NC)"; exit 1; }
	@command -v docker >/dev/null 2>&1 || { echo -e "$(RED)错误: 未找到 docker$(NC)"; exit 1; }
	@echo -e "$(GREEN)[2/4] 设置后端 Python 虚拟环境...$(NC)"
	@cd $(BACKEND_DIR) && \
		test -d .venv || python3 -m venv .venv && \
		.venv/bin/pip install --upgrade pip && \
		.venv/bin/pip install -r requirements.txt
	@echo -e "$(GREEN)[3/4] 安装前端依赖...$(NC)"
	@cd $(FRONTEND_DIR) && npm install
	@echo -e "$(GREEN)[4/4] 复制环境变量文件...$(NC)"
	@cd $(BACKEND_DIR) && test -f .env || cp .env.example .env
	@echo -e "$(GREEN)✓ 开发环境搭建完成！$(NC)"
	@echo -e "  运行 $(YELLOW)make dev$(NC) 启动开发环境"

dev: ## 启动开发环境（Docker Compose）
	$(DC_DEV) up --build

dev-down: ## 停止开发环境
	$(DC_DEV) down

dev-bg: ## 后台启动开发环境
	$(DC_DEV) up --build -d

# ============================================================
# 生产环境
# ============================================================

build: ## 构建生产镜像
	$(DC) build --no-cache

up: ## 启动生产环境
	$(DC) up -d

down: ## 停止生产环境
	$(DC) down

restart: ## 重启所有服务
	$(DC) restart

logs: ## 查看所有服务日志
	$(DC) logs -f

logs-backend: ## 查看后端日志
	$(DC) logs -f backend

logs-frontend: ## 查看前端日志
	$(DC) logs -f frontend

# ============================================================
# 数据库管理
# ============================================================

db-migrate: ## 生成新的 Alembic 迁移文件（用法: make db-migrate MSG="描述"）
	@cd $(BACKEND_DIR) && \
		.venv/bin/alembic revision --autogenerate -m "$(MSG)"

db-upgrade: ## 执行数据库迁移（升级到最新版本）
	@cd $(BACKEND_DIR) && \
		.venv/bin/alembic upgrade head
	@echo -e "$(GREEN)✓ 数据库迁移完成$(NC)"

db-downgrade: ## 回退一次数据库迁移
	@cd $(BACKEND_DIR) && \
		.venv/bin/alembic downgrade -1

db-reset: ## 重置数据库（删除所有数据并重新迁移）
	@echo -e "$(RED)警告: 此操作将删除所有数据！$(NC)"
	@read -p "确认执行? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@cd $(BACKEND_DIR) && \
		.venv/bin/alembic downgrade base && \
		.venv/bin/alembic upgrade head
	@echo -e "$(GREEN)✓ 数据库已重置$(NC)"

db-history: ## 查看迁移历史
	@cd $(BACKEND_DIR) && .venv/bin/alembic history

# ============================================================
# 测试与代码质量
# ============================================================

test: ## 运行所有测试
	@echo -e "$(GREEN)运行后端测试...$(NC)"
	@cd $(BACKEND_DIR) && .venv/bin/pytest tests/ -v --tb=short
	@echo -e "$(GREEN)✓ 测试完成$(NC)"

test-cov: ## 运行测试并生成覆盖率报告
	@cd $(BACKEND_DIR) && \
		.venv/bin/pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

lint: ## 代码检查（后端）
	@cd $(BACKEND_DIR) && \
		.venv/bin/python -m flake8 app/ tests/ --max-line-length=120 --ignore=E501,W503
	@echo -e "$(GREEN)✓ 代码检查通过$(NC)"

# ============================================================
# 部署
# ============================================================

deploy: ## 生产环境部署
	@bash $(PROJECT_ROOT)/scripts/deploy.sh

health: ## 检查所有服务健康状态
	@echo -e "$(GREEN)检查服务健康状态...$(NC)"
	@$(DC) ps
	@echo ""
	@echo -e "$(GREEN)后端健康检查:$(NC)"
	@curl -sf http://localhost:8000/health 2>/dev/null && echo "" || echo -e "$(RED)后端服务不可用$(NC)"
	@echo -e "$(GREEN)前端健康检查:$(NC)"
	@curl -sf http://localhost:3000 2>/dev/null && echo "" || echo -e "$(RED)前端服务不可用$(NC)"

# ============================================================
# 清理
# ============================================================

clean: ## 清理构建产物和临时文件
	@echo -e "$(YELLOW)清理临时文件...$(NC)"
	@find $(PROJECT_ROOT) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find $(PROJECT_ROOT) -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find $(PROJECT_ROOT) -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf $(FRONTEND_DIR)/dist 2>/dev/null || true
	@echo -e "$(GREEN)✓ 清理完成$(NC)"

clean-docker: ## 清理 Docker 资源（容器、镜像、卷）
	@echo -e "$(RED)警告: 此操作将删除所有 OpenWork Docker 资源！$(NC)"
	@read -p "确认执行? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	$(DC) down -v --rmi local
	@echo -e "$(GREEN)✓ Docker 资源已清理$(NC)"
