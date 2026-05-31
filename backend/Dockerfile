# ============================================================
# OpenWork 后端 Dockerfile
# 多阶段构建，优化镜像体积
# ============================================================

# ---- 构建阶段：安装 Python 依赖 ----
FROM python:3.12-slim AS builder

WORKDIR /build

# 安装编译依赖（部分 Python 包需要编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- 开发阶段：用于 docker-compose dev 热重载 ----
FROM python:3.12-slim AS development

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- 生产阶段：最小化镜像 ----
FROM python:3.12-slim AS production

# 添加安全元数据
LABEL maintainer="OpenWork Team"
LABEL description="OpenWork 可信任务市场后端服务"

# 创建非 root 用户
RUN groupadd -r openwork && useradd -r -g openwork -d /app -s /sbin/nologin openwork

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# 复制已安装的 Python 包
COPY --from=builder /install /usr/local

WORKDIR /app

# 复制应用代码
COPY . .

# 修改文件所有权
RUN chown -R openwork:openwork /app

# 切换到非 root 用户
USER openwork

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
