# ================================================================
# LLM 知识库 — Docker 镜像
# 用于 Railway / Render / Fly.io / 本地容器部署
#
# 构建：  docker build -t llm-kb .
# 运行：  docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... llm-kb
# ================================================================

FROM python:3.11-slim

# 系统依赖（PDF 支持需要 libmupdf）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt web/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r web/requirements.txt

# 复制项目代码
COPY . .

# 创建运行时目录（挂载 volume 时会被覆盖）
RUN mkdir -p raw/articles raw/papers raw/media-notes wiki/.state

# 暴露端口
EXPOSE 8000

# 启动命令（PORT 环境变量兼容 Railway/Render 自动注入）
CMD uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}
