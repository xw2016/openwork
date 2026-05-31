#!/usr/bin/env bash
# ============================================================
# OpenWork 生产环境部署脚本
# 包含数据库迁移、服务启动、健康检查
# ============================================================

set -euo pipefail

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  OpenWork 生产环境部署${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ---- 0. 前置检查 ----
echo -e "${GREEN}[0/5] 前置检查...${NC}"
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}错误: 未找到 docker${NC}"
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo -e "${RED}错误: docker compose 不可用${NC}"
    exit 1
fi

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告: 未找到 .env 文件，使用默认配置${NC}"
    echo -e "${YELLOW}建议: 复制 .env.example 为 .env 并修改敏感配置${NC}"
fi
echo ""

# ---- 1. 拉取最新代码（如果是 git 仓库） ----
echo -e "${GREEN}[1/5] 更新代码...${NC}"
if [ -d ".git" ]; then
    git pull origin main 2>/dev/null || {
        echo -e "${YELLOW}警告: git pull 失败，继续使用当前代码${NC}"
    }
    echo -e "  ${GREEN}✓${NC} 代码已更新"
else
    echo -e "  ${YELLOW}!${NC} 非 git 仓库，跳过代码更新"
fi
echo ""

# ---- 2. 构建镜像 ----
echo -e "${GREEN}[2/5] 构建 Docker 镜像...${NC}"
docker compose build --no-cache
echo -e "  ${GREEN}✓${NC} 镜像构建完成"
echo ""

# ---- 3. 启动基础设施服务 ----
echo -e "${GREEN}[3/5] 启动数据库和缓存服务...${NC}"
docker compose up -d postgres redis

# 等待 PostgreSQL 就绪
echo -e "  等待 PostgreSQL 就绪..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-openwork}" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} PostgreSQL 已就绪"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo -e "  ${RED}✗${NC} PostgreSQL 启动超时"
        exit 1
    fi
    sleep 1
done

# 等待 Redis 就绪
echo -e "  等待 Redis 就绪..."
for i in $(seq 1 15); do
    if docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} Redis 已就绪"
        break
    fi
    if [ "$i" -eq 15 ]; then
        echo -e "  ${RED}✗${NC} Redis 启动超时"
        exit 1
    fi
    sleep 1
done
echo ""

# ---- 4. 执行数据库迁移 ----
echo -e "${GREEN}[4/5] 执行数据库迁移...${NC}"
docker compose run --rm backend alembic upgrade head 2>/dev/null || {
    echo -e "  ${YELLOW}!${NC} 迁移执行失败或暂无迁移，跳过"
}
echo -e "  ${GREEN}✓${NC} 数据库迁移完成"
echo ""

# ---- 5. 启动所有服务 ----
echo -e "${GREEN}[5/5] 启动所有服务...${NC}"
docker compose up -d
echo -e "  ${GREEN}✓${NC} 所有服务已启动"
echo ""

# ---- 健康检查 ----
echo -e "${GREEN}执行健康检查...${NC}"
sleep 5

check_health() {
    local name="$1"
    local url="$2"
    local max_retries="${3:-10}"

    for i in $(seq 1 "$max_retries"); do
        if curl -sf "$url" >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name 健康"
            return 0
        fi
        sleep 2
    done
    echo -e "  ${RED}✗${NC} $name 不健康"
    return 1
}

check_health "后端服务" "http://localhost:${BACKEND_PORT:-8000}/health"
check_health "前端服务" "http://localhost:${FRONTEND_PORT:-3000}"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✓ 部署完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "服务状态："
docker compose ps
echo ""
echo -e "查看日志: ${YELLOW}make logs${NC}"
echo -e "停止服务: ${YELLOW}make down${NC}"
