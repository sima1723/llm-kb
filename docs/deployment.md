# 部署指南 — GitHub Actions + 云服务器

本文档覆盖两条部署路径：

| 路径 | 适合场景 |
|------|---------|
| **A. 自动编译（GitHub Actions）** | 推送 raw 文件 → Actions 自动编译 → wiki 更新回仓库 |
| **B. Web 界面上线** | 把 Web 界面部署到公网服务器（VPS / Railway / Render / Fly.io） |

两条路径可以独立使用，也可以组合：自动编译 + Web 界面同时在线。

---

## 路径 A：GitHub Actions 自动编译 Wiki

### 原理

```
你本地写 raw/articles/xxx.md
        ↓  git push
GitHub Actions 触发
        ↓  pip install + python compile_wiki.py
LLM 编译成 wiki/*.md
        ↓  git commit + git push [skip ci]
仓库中 wiki/ 自动更新
```

### 第一步：把仓库推到 GitHub

```bash
# 如果还没有 GitHub 仓库
gh repo create llm-kb --private   # 私有仓库（推荐，保护原始笔记）
git remote add origin git@github.com:你的用户名/llm-kb.git
git push -u origin master
```

### 第二步：添加 Secret

打开仓库页面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret 名 | 值 | 必填 |
|-----------|-----|------|
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` | 必须 |
| `ANTHROPIC_BASE_URL` | `https://api.relay.example.com` | 可选（使用中转服务时填，留空则走官方 API） |

**如何添加：**

1. 仓库页面顶部点 **Settings**
2. 左侧菜单 → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**
4. Name 填 `ANTHROPIC_API_KEY`，Secret 填你的 Key，点 **Add secret**
5. 如果使用中转服务，重复上步添加 `ANTHROPIC_BASE_URL`

> Secrets 内容加密存储，日志中自动打码，不会泄露。

### 第三步：工作流文件已就位

仓库中已有 `.github/workflows/compile.yml`，推送即生效。

**触发条件：**
- 推送到 `master`/`main` 且 `raw/**` 有变更 → 自动增量编译
- 每天 UTC 18:00（北京时间 02:00）定时检查
- Actions 页面手动触发（可选全量重编译）

### 第四步：验证运行

1. 向 `raw/articles/` 添加一个 `.md` 文件并推送
2. 打开仓库 → **Actions** 标签页
3. 看到 "自动编译 Wiki" 工作流运行
4. 运行完成后，`wiki/` 目录会出现新的提交

### 注意事项

- 提交信息含 `[skip ci]` 防止 wiki 更新再次触发编译（无限循环）
- 编译失败不会推送，仓库状态保持干净
- 费用由 `config.yaml` 中 `budget_limit_usd` 控制

---

## 路径 B：Web 界面部署

### B1. Railway（最简单，推荐新手）

Railway 支持从 GitHub 仓库一键部署，有免费额度。

#### 步骤

1. 打开 [railway.app](https://railway.app) → 用 GitHub 登录

2. 点击 **New Project** → **Deploy from GitHub repo** → 选择你的 `llm-kb` 仓库

3. Railway 自动检测 `Dockerfile` 并构建

4. 添加环境变量：
   - 点击项目 → **Variables** → **New Variable**
   - `ANTHROPIC_API_KEY` = `sk-ant-...`

5. 添加持久化存储（**重要**，否则 raw/ 和 wiki/ 重启后清空）：
   - 点击 **New** → **Volume**
   - 挂载路径填 `/app`（覆盖整个工作目录）
   - 这样 raw/、wiki/、.state/ 都会持久化

6. 访问 Railway 分配的域名即可

> **免费额度**：每月 $5 赠金，够轻量应用跑一整月。

#### railway.json（可选自定义）

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE"
  },
  "deploy": {
    "startCommand": "uvicorn web.app:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

---

### B2. Render

1. 打开 [render.com](https://render.com) → 用 GitHub 登录

2. **New** → **Web Service** → 连接仓库

3. 配置：
   ```
   Runtime:        Docker
   Branch:         master
   Build Command:  （留空，用 Dockerfile）
   Start Command:  uvicorn web.app:app --host 0.0.0.0 --port $PORT
   ```

4. 添加环境变量 `ANTHROPIC_API_KEY`

5. 添加 Disk（持久化存储）：
   - **Add Disk** → Mount Path: `/app` → Size: 1 GB

> Render 免费层会在 15 分钟无访问后休眠，冷启动约 30 秒。

---

### B3. Fly.io（推荐，支持持久化卷，免费层稳定）

```bash
# 安装 flyctl
curl -L https://fly.io/install.sh | sh

# 登录
fly auth login

# 进入项目目录，初始化
cd llm-kb
fly launch --no-deploy     # 自动读取 Dockerfile，生成 fly.toml

# 创建持久化卷（1GB，保存 raw/ wiki/ .state/）
fly volumes create llm_kb_data --size 1 --region hkg  # 香港节点，延迟低

# 设置 API Key
fly secrets set ANTHROPIC_API_KEY=sk-ant-...

# 部署
fly deploy
```

**编辑 `fly.toml`**（fly launch 自动生成，补充挂载配置）：

```toml
app = "llm-kb"
primary_region = "hkg"

[build]

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true

[[mounts]]
  source      = "llm_kb_data"
  destination = "/app"          # 挂载到 /app，覆盖整个工作目录
```

```bash
# 再次部署（应用 fly.toml 挂载配置）
fly deploy

# 查看日志
fly logs

# 打开浏览器
fly open
```

> Fly.io 免费层：3 个共享 CPU 机器 + 3GB 持久化存储，个人用够用。

---

### B4. VPS 自托管（完全控制）

适合已有云服务器（腾讯云、阿里云、AWS、Vultr 等）的用户。

#### 4.1 服务器初始化

```bash
# 登录服务器
ssh user@your-server-ip

# 安装 Python 3.11
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip git

# 克隆仓库
git clone git@github.com:你的用户名/llm-kb.git /home/ubuntu/llm-kb
cd /home/ubuntu/llm-kb

# 安装依赖
pip3 install -r requirements.txt -r web/requirements.txt

# 写入 API Key
python3 -c "
import yaml
cfg = {}
try:
    cfg = yaml.safe_load(open('config.yaml').read()) or {}
except: pass
cfg['api_key'] = 'sk-ant-你的key'
open('config.yaml','w').write(yaml.dump(cfg, allow_unicode=True))
print('✓ API Key 已写入 config.yaml')
"
```

#### 4.2 配置 systemd 服务（开机自启 + 崩溃自重启）

```bash
sudo nano /etc/systemd/system/llm-kb.service
```

填入：

```ini
[Unit]
Description=LLM 知识库 Web 服务
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/llm-kb
ExecStart=/usr/bin/python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
# 启动并设为开机自启
sudo systemctl daemon-reload
sudo systemctl enable llm-kb
sudo systemctl start llm-kb
sudo systemctl status llm-kb   # 确认 active (running)
```

#### 4.3 Nginx 反向代理（可选，支持域名 + HTTPS）

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

sudo nano /etc/nginx/sites-available/llm-kb
```

```nginx
server {
    server_name kb.yourdomain.com;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection keep-alive;
        proxy_set_header   Host $host;
        proxy_cache_bypass $http_upgrade;
        # SSE 需要关闭缓冲
        proxy_buffering    off;
        proxy_read_timeout 3600s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/llm-kb /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 申请 HTTPS 证书
sudo certbot --nginx -d kb.yourdomain.com
```

#### 4.4 启用 GitHub Actions 自动部署到 VPS

`.github/workflows/deploy.yml` 已就位，配置以下 Secrets：

| Secret | 值 |
|--------|-----|
| `DEPLOY_HOST` | 服务器 IP 或域名 |
| `DEPLOY_USER` | SSH 用户名（如 `ubuntu`） |
| `DEPLOY_KEY` | SSH 私钥（`cat ~/.ssh/id_rsa`，在本机生成后把公钥加到服务器） |
| `DEPLOY_PATH` | `/home/ubuntu/llm-kb` |

配置完成后，每次 `git push master` 都会自动 SSH 进服务器、`git pull`、重启服务。

---

## 架构总览

```
本地开发环境
    │
    ├── 写 raw/ 笔记
    │       ↓  git push
    │
GitHub 仓库
    │
    ├── Actions: compile.yml
    │       ↓  LLM 编译 wiki/
    │       ↓  自动 commit + push [skip ci]
    │
    └── Actions: deploy.yml（可选）
            ↓  SSH → git pull → systemctl restart
            ↓
        VPS / Railway / Render / Fly.io
            ↓
        http://your-domain.com:8000
            ↓
        浏览器访问知识图谱
```

---

## 费用对比

| 平台 | 免费额度 | 付费 | 持久化存储 | 推荐指数 |
|------|---------|------|-----------|---------|
| Railway | $5/月赠金 | ~$5-10/月 | 需付费 volume | ⭐⭐⭐⭐ 最简单 |
| Render | 免费层（会休眠） | $7/月起 | 需付费 disk | ⭐⭐⭐ |
| Fly.io | 3机器+3GB免费 | 按量计费 | 免费 3GB | ⭐⭐⭐⭐⭐ 最划算 |
| VPS（腾讯/阿里） | 首年优惠 | ~¥50-100/月 | 本地磁盘 | ⭐⭐⭐⭐ 完全控制 |
| GitHub Actions | 2000分钟/月免费 | $0.008/分钟 | N/A（仅CI） | ✓ 编译用 |

> Actions 编译一次约 2-5 分钟，免费额度够每天跑好几次。

---

## 常见问题

**Q: Actions 编译失败怎么排查？**

打开 Actions → 点击失败的 run → 展开 "编译 Wiki" 步骤查看日志。
常见原因：`ANTHROPIC_API_KEY` 未设置、`budget_limit_usd` 不足。

**Q: 部署到 Railway/Fly.io 后 wiki 内容空了？**

未挂载持久化卷，重新部署时容器被重置。
按 B1/B3 步骤添加 Volume 挂载到 `/app`。

**Q: 同时用 Actions 编译 + VPS 托管，wiki 如何同步？**

VPS 上的 `deploy.yml` 执行 `git pull`，会拉取 Actions 提交的 wiki 变更。
两者自然同步，无需额外操作。

**Q: 私有仓库 Actions 能用吗？**

可以，免费账户每月有 2000 分钟私有仓库 Actions 额度。

**Q: 如何防止 raw/ 笔记被公开？**

使用**私有仓库**（`gh repo create --private`）。
Railway/Render/Fly.io 连接私有仓库无需额外配置。
