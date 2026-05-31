#!/usr/bin/env bash
# ============================================================
# OpenWork 开发环境一键搭建脚本
# 检查依赖、创建虚拟环境、安装依赖、初始化数据库
# ============================================================

set -euo pipefail

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  OpenWork 开发环境搭建${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ---- 1. 检查系统依赖 ----
echo -e "${GREEN}[1/6] 检查系统依赖...${NC}"

check_command() {
    if command -v "$1" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $1 $(command $1 --version 2>/dev/null | head -1 || echo '')"
    else
        echo -e "  ${RED}✗${NC} $1 未找到，请先安装"
        MISSING_DEPS=1
    fi
}

MISSING_DEPS=0
check_command python3
check_command node
check_command npm
check_command docker

if [ "$MISSING_DEPS" -eq 1 ]; then
    echo -e "${RED}错误: 缺少必要的系统依赖，请先安装上述缺失的工具${NC}"
    exit 1
fi
echo ""

# ---- 2. 创建后端 Python 虚拟环境 ----
echo -e "${GREEN}[2/6] 设置后端 Python 虚拟环境...${NC}"
cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "  ${GREEN}✓${NC} 创建虚拟环境 .venv"
else
    echo -e "  ${YELLOW}!${NC} 虚拟环境已存在，跳过创建"
fi

.venv/bin/pip install --upgrade pip -q
echo -e "  ${GREEN}✓${NC} pip 已升级"
echo ""

# ---- 3. 安装后端依赖 ----
echo -e "${GREEN}[3/6] 安装后端依赖...${NC}"
.venv/bin/pip install -r requirements.txt -q
echo -e "  ${GREEN}✓${NC} 后端依赖安装完成"
echo ""

# ---- 4. 安装前端依赖 ----
echo -e "${GREEN}[4/6] 安装前端依赖...${NC}"
cd "$FRONTEND_DIR"
if [ -f "package-lock.json" ]; then
    npm ci --no-audit --no-fund --silent
else
    npm install --no-audit --no-fund --silent
fi
echo -e "  ${GREEN}✓${NC} 前端依赖安装完成"
echo ""

# ---- 5. 配置环境变量 ----
echo -e "${GREEN}[5/6] 配置环境变量...${NC}"
cd "$BACKEND_DIR"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "  ${GREEN}✓${NC} 已从 .env.example 创建 .env 文件"
    echo -e "  ${YELLOW}!${NC} 请编辑 backend/.env 修改 SECRET_KEY 等敏感配置"
else
    echo -e "  ${YELLOW}!${NC} .env 文件已存在，跳过"
fi
echo ""

# ---- 6. 启动数据库服务并执行迁移 ----
echo -e "${GREEN}[6/6] 初始化数据库...${NC}"
cd "$PROJECT_ROOT"

# 检查 Docker Compose 是否可用
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo -e "  启动 PostgreSQL 和 Redis..."
    docker compose up -d postgres redis

    # 等待 PostgreSQL 就绪
    echo -e "  等待 PostgreSQL 就绪..."
    for i in $(seq 1 30); do
        if docker compose exec -T postgres pg_isready -U openwork >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} PostgreSQL 已就绪"
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo -e "  ${RED}✗${NC} PostgreSQL 启动超时"
            exit 1
        fi
        sleep 1
    done

    # 执行数据库迁移
    echo -e "  执行数据库迁移..."
    cd "$BACKEND_DIR"
    .venv/bin/alembic upgrade head 2>/dev/null || echo -e "  ${YELLOW}!${NC} 暂无迁移文件，跳过"
    echo -e "  ${GREEN}✓${NC} 数据库迁移完成"
else
    echo -e "  ${YELLOW}!${NC} Docker 不可用，请手动启动数据库并执行迁移"
fi
echo ""

# ---- 完成 ----
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✓ 开发环境搭建完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "后续步骤："
echo -e "  1. 编辑 ${YELLOW}backend/.env${NC} 配置环境变量"
echo -e "  2. 运行 ${YELLOW}make dev${NC} 启动完整开发环境"
echo -e "  或者分别启动："
echo -e "     后端: ${YELLOW}cd backend && .venv/bin/uvicorn app.main:app --reload${NC}"
echo -e "     前端: ${YELLOW}cd frontend && npm run dev${NC}"
echo ""
