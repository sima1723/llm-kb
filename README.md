# LLM 知识库

> 把 PDF、网页、视频字幕、手动笔记编译成结构化的个人 wiki，用 LLM 驱动搜索、问答与知识生成。
> 提供 **Web 界面**（知识图谱 + 问答）和 **命令行**两种使用方式。

灵感来自 [Andrej Karpathy](https://karpathy.ai) 提倡的"LLM 知识外脑"概念：
知识不仅要记录，更要**可搜索、可追问、可互相关联**，让知识库越用越智能。

---

## 核心理念

```
原始资料（PDF / 网页 / 视频 / 笔记）
        ↓  LLM 编译
结构化 wiki（Markdown 条目 + [[双向链接]]）
        ↓  TF-IDF / LLM 语义搜索
问答 → 答案回流 → wiki 持续生长
```

- **无向量数据库**：纯 Markdown 文件 + TF-IDF，零额外基础设施
- **LLM 作"研究员"**：提取概念、建立关联、去重合并，不只是存储
- **知识图谱可视化**：Web 界面用 d3-force 展示条目与链接关系
- **答案回流**：每次问答的答案都写回知识库，越用越智能

---

## 快速开始

### 方式一：Web 界面（推荐）

```bash
git clone <repo-url> llm-kb && cd llm-kb

# 安装依赖（CLI + Web）
pip install -r requirements.txt
pip install -r web/requirements.txt

# 启动 Web 服务
make web
# 浏览器打开 http://localhost:8000
# 首次访问按提示填入 Anthropic API Key 即可
```

### 方式二：纯命令行

```bash
git clone <repo-url> llm-kb && cd llm-kb

export ANTHROPIC_API_KEY=sk-ant-...
make init                              # 安装依赖 + 初始化目录

make clip URL=https://example.com/article   # 摄入网页
make compile                                # 编译成 wiki
make ask-save Q="什么是 Transformer?"       # 问答并保存
```

---

## 部署指南

### 环境要求

- Python 3.10+
- pip
- Git（可选，用于 wiki 版本快照）

### 一、安装依赖

```bash
# CLI 核心依赖
pip install -r requirements.txt

# Web 界面额外依赖（FastAPI + uvicorn）
pip install -r web/requirements.txt

# 可选：PDF 支持
pip install pymupdf

# 可选：YouTube 字幕提取
pip install yt-dlp

# 可选：语音转录（无字幕时降级）
pip install openai-whisper
```

### 二、配置 API Key

**方式 A — 通过 Web 界面（推荐）**

启动后访问 `http://localhost:8000`，首次进入会弹出配置页，填入 API Key 点击「测试连接」即可。

**方式 B — 编辑 config.yaml**

```yaml
api_key: "sk-ant-..."          # Anthropic API Key
base_url: ""                   # 留空用官方；填中转地址如 https://api.relay.example.com
```

**方式 C — 环境变量**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

> API Key 获取：[console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key  
> 首充 $5 可编译约 100 篇中等文章。

### 三、启动服务

```bash
# 默认 8000 端口
make web

# 自定义端口
PORT=9000 make web

# 或直接用 uvicorn
uvicorn web.app:app --reload --port 8000
```

### 四、初始化目录结构（仅 CLI 模式需要）

```bash
make init
```

会自动创建 `raw/`、`wiki/`、`.state/` 等目录。

---

## Web 界面使用

打开 `http://localhost:8000` 后：

| 功能 | 操作 |
|------|------|
| **添加网页** | 点「+ 添加内容」→「网页 URL」，粘贴 URL 后点「抓取并编译」 |
| **添加 PDF** | 点「+ 添加内容」→「上传 PDF」，拖入文件自动处理 |
| **添加视频** | 点「+ 添加内容」→「视频字幕」，粘贴 YouTube 地址 |
| **搜索** | 顶部搜索框，≤15字 走 TF-IDF，>15字 自动转 LLM 问答 |
| **生成报告/幻灯片** | 点「⚡ 生成」，输入主题，选格式（报告/幻灯片/摘要） |
| **填充 stub** | 点「⚡ 生成」底部，查看待填充条目并一键 AI 填充 |
| **查看图谱** | 主界面即为知识图谱，点击节点查看条目详情 |
| **设置** | 点「设置」修改 API Key、预算上限、git 自动提交 |

---

## 命令行参考

### 数据摄入

```bash
make clip URL=<url>                    # 抓取网页
make clip-video URL=<url>             # 提取 YouTube 字幕（需 yt-dlp）
make clip-video URL=<url> WHISPER=1   # 无字幕时降级 Whisper 转录
make extract PDF=<path>               # 提取 PDF
make note TITLE=<标题>                 # 新建手动笔记
```

### 编译

```bash
make compile              # 增量编译（只处理新/变更文件）
make compile-full         # 全量重编译
make compile-commit       # 编译 + 自动 git commit wiki/
make compile-dry          # 预览待处理文件（不调用 API）
```

### 搜索与问答

```bash
make search Q=<关键词>          # TF-IDF 搜索
make search-semantic Q=<问题>   # LLM 语义搜索（支持跨语言/近义词）
make ask Q=<问题>               # 问答
make ask-save Q=<问题>          # 问答 + 答案写回 wiki（推荐）
make ask-deep Q=<问题>          # 深度问答（递归读取关联条目）
```

### 生成

```bash
make slides TOPIC=<主题>    # 生成 Marp 格式幻灯片（保存至 wiki/slides/）
make report TOPIC=<主题>    # 生成完整 Markdown 报告（保存至 wiki/answers/）
make brief TOPIC=<主题>     # 生成一段话摘要
```

### 维护

```bash
make lint              # 健康检查（断链 / 孤立条目 / 格式问题）
make lint-fix          # 自动修复可修复问题
make lint-ai           # AI 修复复杂问题
make explore           # 分析知识库，给出探索建议
make explore-add       # 探索 + 自动创建 stub 占位条目
make stub-fill         # 用 LLM 填充所有 stub 条目
make stub-fill ENTRY=<名称>   # 只填充指定条目
make stats             # 统计仪表盘
make status            # 快速状态（待处理数 + 条目数）
```

---

## 目录结构

```
llm-kb/
├── raw/                    # 原始输入资料（编译前）
│   ├── articles/           #   网页文章
│   ├── papers/             #   论文（.md 或 .pdf）
│   ├── repos/              #   代码仓库笔记
│   └── media-notes/        #   视频 / 播客字幕
│
├── wiki/                   # 编译后的结构化知识库
│   ├── INDEX.md            #   自动生成的条目索引
│   ├── *.md                #   wiki 条目（概念名.md）
│   ├── answers/            #   问答记录（答案回流）
│   └── slides/             #   生成的 Marp 幻灯片
│
├── web/                    # Web 界面
│   ├── app.py              #   FastAPI 入口
│   ├── api/                #   API 路由（config/ingest/compile/wiki/query/generate/maintenance）
│   ├── static/             #   前端（Vanilla JS + d3-force + marked.js）
│   └── requirements.txt    #   Web 依赖
│
├── tools/                  # 命令行工具
│   ├── compile_wiki.py     #   编译主引擎（LLM 提取 + 去重 + 增量）
│   ├── search.py           #   TF-IDF + 语义搜索
│   ├── ask.py              #   问答 + 答案回流
│   ├── slides.py           #   Marp 幻灯片生成
│   ├── report.py           #   报告导出
│   ├── stub_fill.py        #   Stub 条目 AI 填充
│   ├── lint.py             #   健康检查
│   ├── explore.py          #   探索建议
│   ├── stats.py            #   统计仪表盘
│   ├── pdf_to_md.py        #   PDF 提取（PyMuPDF）
│   ├── web_to_md.py        #   网页抓取
│   ├── video_to_md.py      #   视频字幕提取（yt-dlp / Whisper）
│   └── llm_client.py       #   Anthropic API 封装
│
├── templates/              # LLM Prompt 模板
├── .state/                 # 编译状态（hash 缓存 / 断点续传）
├── config.yaml             # 配置文件
├── requirements.txt        # CLI 依赖
└── Makefile                # 命令入口（make help 查看全部）
```

---

## 配置说明

`config.yaml` 完整注释版：

```yaml
api_key: ""          # Anthropic API Key（或留空用环境变量）
base_url: ""         # 中转 API 地址（留空 = 官方）

llm:
  model: "claude-sonnet-4-20250514"
  max_tokens: 4096
  retry_count: 3
  retry_delay_base: 2        # 失败重试指数退避基数（秒）
  max_tokens_by_tool:        # 按工具覆盖 token 上限
    compile: 8192
    ask: 4096
    slides: 3000

compile:
  max_file_size_kb: 50       # 超出则自动分段
  budget_limit_usd: 5.0      # 单次编译费用上限（超出报错）
  input_price_per_mtok: 3.0
  output_price_per_mtok: 15.0
  git_auto_commit: false     # 编译后自动 git commit wiki/

wiki:
  language: "zh"             # 条目语言
  min_entry_length: 100      # 最短条目字数（lint 检查用）
```

---

## 费用估算

| 操作 | 约花费 |
|------|--------|
| 编译 1 篇文章（~2000字） | ~$0.05 |
| 编译 10 篇文章 | ~$0.30–0.80 |
| 编译 50 篇文章 | ~$2–5 |
| 一次问答 | ~$0.01–0.03 |
| 生成报告/幻灯片 | ~$0.03–0.08 |
| Stub 填充（每条） | ~$0.02–0.05 |

通过 `config.yaml` 的 `compile.budget_limit_usd` 设置单次上限，超出自动中止。

---

## 与 Obsidian 配合

`wiki/` 目录可直接在 Obsidian 中打开：
- `[[双向链接]]` 自动渲染为图谱节点
- `wiki/slides/` 中的幻灯片可用 [Marp 插件](https://github.com/samuele-cozzi/obsidian-marp-slides) 预览

---

## FAQ

**Q: 为什么不用向量数据库？**  
A: 本地 TF-IDF（中文 bigram 分词）对个人知识库检索效果已足够，零部署、零依赖、可离线。复杂语义查询由 LLM 负责。

**Q: 编译失败了怎么办？**  
A: 单文件失败不影响其他文件。`.state/` 记录已处理文件，重新运行 `make compile` 自动跳过成功文件、重试失败文件。

**Q: 支持哪些模型？**  
A: 任何 Anthropic 支持的模型，修改 `config.yaml` 中 `llm.model` 即可。也支持兼容 Anthropic API 格式的中转服务（填 `base_url`）。

**Q: 答案回流是什么意思？**  
A: `make ask-save` 或 Web 问答时，LLM 的回答会保存到 `wiki/answers/`，下次搜索时会被检索到并作为上下文，让知识库持续积累。

**Q: Web 界面和命令行能同时用吗？**  
A: 可以。Web 界面直接调用 `tools/` 中的相同模块，两者操作的是同一份 `raw/` 和 `wiki/` 目录。
