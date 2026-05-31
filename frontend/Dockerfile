# ============================================================
# OpenWork 前端 Dockerfile
# 支持开发模式 (development) 和生产模式 (production) 两个阶段
# ============================================================

# ---- 基础阶段：安装依赖 ----
FROM node:20-alpine AS base
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

# ---- 开发阶段：使用 Vite 开发服务器 ----
FROM base AS development
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---- 构建阶段：编译生产资源 ----
FROM base AS build
COPY . .
RUN npm run build

# ---- 生产阶段：Nginx 静态服务 ----
FROM nginx:1.25-alpine AS production

# 移除默认配置
RUN rm /etc/nginx/conf.d/default.conf

# 复制自定义 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 从构建阶段复制静态资源
COPY --from=build /app/dist /usr/share/nginx/html

# 创建非 root 用户运行 nginx
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
