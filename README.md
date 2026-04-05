# LLM Knowledge Base

> 个人知识库自动化工具 — 把 PDF、网页、笔记编译成结构化 wiki，用 LLM 驱动搜索与问答。

灵感来自 [Andrej Karpathy](https://karpathy.ai) 提倡的"知识外脑"概念：
学到的东西不仅要记录，更要**可搜索、可追问、可互相关联**，让知识库越用越智能。

---

## 快速开始（5步）

```bash
# 1. 克隆仓库
git clone <repo-url> llm-kb
cd llm-kb

# 2. 安装依赖 + 初始化
export ANTHROPIC_API_KEY=sk-ant-...
make init

# 3. 放入原始资料（任选其一）
make clip URL=https://example.com/article
make note TITLE="Transformer 论文笔记"
# 或手动把 .md 文件放到 raw/articles/

# 4. 编译成 wiki
make compile

# 5. 搜索和提问
make search Q="注意力机制"
make ask-save Q="什么是 Transformer?"
```

---

## 完整命令参考

### 数据摄入

| 命令 | 说明 |
|------|------|
| `make clip URL=<url>` | 抓取网页到 `raw/articles/` |
| `make clip-video URL=<url>` | 提取 YouTube 字幕到 `raw/media-notes/`（需 `pip install yt-dlp`）|
| `make clip-video URL=<url> WHISPER=1` | 字幕不可用时降级到 Whisper 转录（需 `pip install openai-whisper`）|
| `make extract PDF=<path>` | 提取 PDF 文字到 `raw/papers/` |
| `make note TITLE=<标题> TYPE=<类型>` | 新建手动笔记（article/paper/media-note） |

### 编译

| 命令 | 说明 |
|------|------|
| `make compile` | 增量编译（只处理新文件） |
| `make compile-commit` | 增量编译 + 编译结束后自动 `git commit wiki/` |
| `make compile-full` | 全量重编译所有 raw 文件 |
| `make compile-dry` | 预览待处理文件（不调用 API） |

### 搜索与问答

| 命令 | 说明 |
|------|------|
| `make search Q=<关键词>` | TF-IDF 全文搜索 wiki |
| `make search-semantic Q=<问题>` | LLM 语义搜索（跨语言/近义词/概念级查询） |
| `make list` | 列出所有 wiki 条目 |
| `make show Q=<条目名>` | 显示条目内容及关联图谱 |
| `make ask Q=<问题>` | 基于知识库回答问题 |
| `make ask-save Q=<问题>` | 回答并保存到 `wiki/answers/`（答案回流） |
| `make ask-deep Q=<问题>` | 深度问答（递归读取关联条目） |
| `make slides TOPIC=<主题>` | 生成 Marp 格式幻灯片 |
| `make report TOPIC=<主题>` | 生成完整 Markdown 报告 |
| `make brief TOPIC=<主题>` | 生成一段话摘要 |

### 维护

| 命令 | 说明 |
|------|------|
| `make lint` | 健康检查（断链/孤立/格式问题） |
| `make lint-fix` | 自动修复本地可修复的问题 |
| `make lint-ai` | 调用 AI 修复复杂问题 |
| `make explore` | 分析知识库，给出探索方向建议 |
| `make explore-add` | 探索建议 + 自动创建 stub 条目 |
| `make stub-fill` | 用 LLM 填充所有"待补充"stub 条目 |
| `make stub-fill ENTRY=<条目名>` | 只填充指定 stub 条目 |
| `make stub-fill-dry` | 预览待填充列表（不调用 API） |
| `make stats` | 统计仪表盘 |
| `make status` | 快速状态（待处理数 + 条目数） |

---

## 目录结构

```
llm-kb/
├── raw/                  # 原始输入资料
│   ├── articles/         # 网页文章（.md）
│   ├── papers/           # 论文（.md 或 .pdf）
│   ├── repos/            # 代码仓库笔记
│   └── media-notes/      # 视频/播客笔记
│
├── wiki/                 # 编译后的知识库
│   ├── INDEX.md          # 自动生成的条目索引
│   ├── *.md              # wiki 条目（概念名.md）
│   ├── answers/          # 问答记录（答案回流）
│   └── slides/           # 生成的幻灯片
│
├── tools/                # 工具代码
│   ├── compile_wiki.py   # 编译主引擎
│   ├── search.py         # TF-IDF 搜索引擎
│   ├── ask.py            # 问答 + 答案回流
│   ├── slides.py         # Marp 幻灯片生成
│   ├── report.py         # 报告导出
│   ├── lint.py           # 健康检查
│   ├── explore.py        # 探索建议
│   ├── stats.py          # 统计仪表盘
│   ├── pdf_to_md.py      # PDF 提取
│   ├── web_to_md.py      # 网页抓取
│   ├── new_note.py       # 笔记模板
│   ├── llm_client.py     # API 封装
│   ├── parser.py         # XML 响应解析
│   ├── chunker.py        # 文件分段
│   ├── indexer.py        # INDEX 生成
│   └── state.py          # 状态管理
│
├── templates/            # Prompt 模板
├── .state/               # 编译状态（处理记录、断点）
├── config.yaml           # 配置文件
├── requirements.txt      # Python 依赖
└── Makefile              # 命令入口
```

---

## 配置说明（config.yaml）

```yaml
llm:
  model: "claude-sonnet-4-20250514"  # 使用的模型
  max_tokens: 8192                   # 单次最大输出 token
  retry_count: 3                     # API 失败重试次数
  retry_delay_base: 2                # 指数退避基数（秒）

compile:
  max_file_size_kb: 50      # 超过此大小的文件自动分段
  budget_limit_usd: 5.0     # 单次 compile 费用上限（超出后报错）
  input_price_per_mtok: 3.0
  output_price_per_mtok: 15.0

wiki:
  language: "zh"             # wiki 条目语言
  min_entry_length: 100      # 最小条目字数（lint 检查用）

paths:
  raw: "raw"
  wiki: "wiki"
  state: ".state"
  templates: "templates"
```

---

## 与 Obsidian 配合使用

`wiki/` 目录可以直接用 Obsidian 打开：

1. Obsidian → 打开文件夹 → 选择 `wiki/`
2. `[[链接]]` 会自动渲染为双向链接
3. `wiki/slides/` 中的幻灯片可用 [Obsidian Marp](https://github.com/samuele-cozzi/obsidian-marp-slides) 插件预览

---

## 费用估算

| 场景 | 约花费 |
|------|--------|
| 编译 1 篇中等文章（~2000字） | ~$0.05 |
| 编译 10 篇文章 | ~$0.30-0.80 |
| 编译 50 篇文章 | ~$2-5（取决于内容长度） |
| 一次问答 | ~$0.01-0.03 |
| 生成幻灯片 | ~$0.03-0.05 |

> 通过 `config.yaml` 中的 `budget_limit_usd` 控制单次最大消费。

---

## FAQ

**Q: 为什么不用 Markdown 文件直接搜索？**  
A: 本地 TF-IDF 搜索已足够快（无需安装向量数据库），且支持中文 bigram 分词，对中文内容检索效果好。

**Q: 编译失败了怎么办？**  
A: 单个文件失败不影响其他文件。失败记录在 `.state/compile_errors/`。再次运行 `make compile` 会自动重试失败的文件。

**Q: 可以用其他模型吗？**  
A: 修改 `config.yaml` 中的 `llm.model` 即可。需要是 Anthropic 支持的模型 ID。

**Q: wiki 条目如何更新？**  
A: 修改 `raw/` 中的源文件，再运行 `make compile`。系统检测到文件 hash 变化会自动重新编译，并用增量 prompt 更新已有条目。

**Q: 答案回流是什么？**  
A: `make ask-save` 保存的答案存入 `wiki/answers/`，下次搜索时会被 TF-IDF 检索到，并作为上下文提供给 LLM。知识库越用越智能。
