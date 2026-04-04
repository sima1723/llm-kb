# LLM Knowledge Base 项目计划

## 一、架构验证：你的理解 vs 补充

你的理解 ✅ 完全正确。补充两个关键闭环：

```
提问 → 搜索wiki → LLM回答 → 答案存回wiki → 下次可被搜索到
       ↑                                        │
       └────────── 探索即积累闭环 ──────────────┘

新增raw文件 → 编译 → 检测已有条目冲突 → 自动合并/标记
                       ↑                        │
                       └─── 自愈合闭环 ─────────┘
```

---

## 二、之前提示词的 9 个遗漏

| # | 遗漏 | 影响 | 修复 |
|---|------|------|------|
| 1 | **没有配置文件** | 模型名、API参数散落在代码里，换模型要改多处 | 加 `config.yaml` |
| 2 | **没有费用控制** | 大量raw文件一次compile可能烧几十美元 | 加 `--budget` 参数和token计数 |
| 3 | **ask.py 答案没有回流** | "探索即积累"断裂，问过的问题不会增强wiki | 答案自动标记为已编译的wiki内容 |
| 4 | **API 返回格式不可靠** | JSON解析失败率高，尤其大量输出时 | 用XML标签替代纯JSON，更鲁棒 |
| 5 | **没有进度显示** | 编译50个文件时用户以为卡死了 | 加 rich 进度条 |
| 6 | **没有 config 驱动的 prompt 模板** | 换语言/换风格要改代码 | prompt 模板外置到 `templates/` |
| 7 | **tools/ 缺少 `__init__.py`** | 模块间无法互相 import | 加包结构 |
| 8 | **没有 dry-run 模式** | 用户无法预览将要发生什么 | 所有命令加 `--dry-run` |
| 9 | **lint 的 API 修复没有纳入** | 教程说用LLM修复矛盾，但lint.py只做本地检查 | 加 `--ai-fix` 模式调API |

---

## 三、完整项目计划（Plan 模式）

### Phase 0: 项目脚手架
**目标**：可运行的空项目，所有目录和配置到位

### Phase 1: 数据摄入层
**目标**：raw/ 目录能自动接收 PDF、网页、手动笔记，统一转为 Markdown

### Phase 2: 编译引擎（核心）
**目标**：读取 raw/，增量生成 wiki/，支持断点续做

### Phase 3: 查询与输出层
**目标**：搜索 + 问答 + 答案回流闭环

### Phase 4: 健康维护
**目标**：自动检测问题 + 本地修复 + AI修复

### Phase 5: 统一入口 + 文档
**目标**：Makefile + README，开箱即用

---

## 四、可执行 Task List（共 28 个任务）

每个任务标注：前置依赖、预计文件、验证方式。
Claude Code 按顺序执行，每完成一个任务 commit 一次。

---

### Phase 0: 项目脚手架（4 个任务）

#### Task 0.1 — 创建目录结构
```
前置：无
创建：
  llm-kb/
  ├── raw/articles/
  ├── raw/papers/
  ├── raw/repos/
  ├── raw/media-notes/
  ├── wiki/answers/
  ├── wiki/slides/
  ├── tools/
  │   └── __init__.py
  ├── templates/
  ├── .state/
  ├── .gitignore
  └── requirements.txt

验证：tree llm-kb 输出结构正确
```

#### Task 0.2 — 创建 config.yaml
```
前置：Task 0.1
文件：llm-kb/config.yaml
内容：
  llm:
    model: "claude-sonnet-4-20250514"
    max_tokens: 8192
    retry_count: 3
    retry_delay_base: 2  # 指数退避基数（秒）
  
  compile:
    max_file_size_kb: 50       # 超过此大小分段处理
    budget_limit_usd: 5.0      # 单次 compile 费用上限
    input_price_per_mtok: 3.0  # Sonnet 输入价格
    output_price_per_mtok: 15.0 # Sonnet 输出价格
  
  wiki:
    language: "zh"             # wiki 条目语言
    min_entry_length: 100      # 最小条目字数
  
  paths:
    raw: "raw"
    wiki: "wiki"
    state: ".state"
    templates: "templates"

验证：python -c "import yaml; yaml.safe_load(open('config.yaml'))" 无报错
```

#### Task 0.3 — 创建 Prompt 模板
```
前置：Task 0.1
文件：
  llm-kb/templates/compile.txt    — 编译 prompt
  llm-kb/templates/incremental.txt — 增量编译 prompt
  llm-kb/templates/ask.txt        — 问答 prompt
  llm-kb/templates/lint_ai.txt    — AI 修复 prompt

每个模板使用 {placeholder} 占位符，由 Python str.format() 填充。

compile.txt 关键设计（用XML标签替代JSON，更鲁棒）：

---模板开始---
你是一位知识库编译器。语言：{language}

## 输入
<raw_content>
{raw_content}
</raw_content>

<current_index>
{index_content}
</current_index>

<related_entries>
{related_entries}
</related_entries>

## 任务
分析原始资料，为每个核心概念生成 wiki 条目。

## 输出格式
对每个条目，用以下格式输出：

<wiki_entry>
<filename>概念名.md</filename>
<action>create 或 update</action>
<content>
---
related_concepts: [概念A, 概念B]
sources: [原始文件名]
last_updated: {today}
---

## 定义
3-5句简洁定义。

## 关键要点
- 要点1
- 要点2

## 详细说明
展开阐述...

## 关联概念
- [[概念A]] — 关系说明
- [[概念B]] — 关系说明

## 来源
- raw/articles/原始文件名.md
</content>
</wiki_entry>

最后输出更新后的索引：
<wiki_entry>
<filename>INDEX.md</filename>
<action>update</action>
<content>索引内容</content>
</wiki_entry>
---模板结束---

验证：所有模板文件存在且包含正确的占位符
```

#### Task 0.4 — 创建状态管理模块
```
前置：Task 0.1
文件：llm-kb/tools/state.py
功能：
  class StateManager:
    def __init__(self, state_dir=".state")
    def get_checkpoint(self, phase: str) -> dict | None
    def set_checkpoint(self, phase: str, data: dict)
    def get_processed_files(self) -> dict
    def mark_file_processed(self, filepath: str, hash: str, outputs: list[str])
    def is_file_processed(self, filepath: str) -> bool  # 比较hash
    def get_unprocessed_files(self, raw_dir: str) -> list[str]
    def file_hash(self, filepath: str) -> str  # sha256

  - 所有数据存为 JSON，读写时加文件锁防并发
  - get_unprocessed_files 返回新增+修改的文件列表

验证：
  python -c "
  from tools.state import StateManager
  sm = StateManager()
  sm.set_checkpoint('test', {'ok': True})
  assert sm.get_checkpoint('test')['ok'] == True
  print('PASS')
  "
```

---

### Phase 1: 数据摄入层（3 个任务）

#### Task 1.1 — PDF 提取工具
```
前置：Task 0.4
文件：llm-kb/tools/pdf_to_md.py
CLI 入口：
  python tools/pdf_to_md.py [文件或目录]
  python tools/pdf_to_md.py --help

功能：
  - 用 PyMuPDF (fitz) 提取文本
  - 按字体大小推断标题层级（最大字体=h1，次大=h2，其余=正文）
  - 表格转 Markdown 表格
  - 输出 YAML frontmatter（source_type, source_file, extracted_at, page_count）
  - 幂等：.md 存在且 mtime > pdf 的 mtime 则跳过
  - rich 进度条显示处理进度
  - --dry-run 模式只列出将处理的文件

验证：
  1. 放一个测试 PDF 到 raw/papers/
  2. 运行 python tools/pdf_to_md.py raw/papers/
  3. 确认生成了同名 .md 文件，内容可读
  4. 再次运行，确认显示"跳过"
```

#### Task 1.2 — 网页抓取工具
```
前置：Task 0.4
文件：llm-kb/tools/web_to_md.py
CLI 入口：
  python tools/web_to_md.py <URL>
  python tools/web_to_md.py --help

功能：
  - 用 urllib + html.parser 提取正文（不依赖 requests/bs4）
  - 文件名：YYYY-MM-DD-标题slug.md（slug 用 title 的前50字符 ASCII 化）
  - YAML frontmatter（source_type, source_url, clipped_at）
  - 图片保留原始 URL，不下载
  - 如果 URL 已被抓取过（检查 frontmatter 中的 source_url），提示并跳过
  - 优雅处理网络错误

验证：
  python tools/web_to_md.py "https://example.com"
  确认 raw/articles/ 下生成了 .md 文件
```

#### Task 1.3 — 手动笔记模板生成器
```
前置：Task 0.1
文件：llm-kb/tools/new_note.py
CLI 入口：
  python tools/new_note.py "笔记标题" [--type article|paper|media-note]

功能：
  - 在对应的 raw/ 子目录生成带 frontmatter 的空模板
  - 默认类型 article
  - frontmatter 包含 source_type, created_at, tags (空列表)
  - 用 $EDITOR 或提示用户手动编辑

验证：
  python tools/new_note.py "测试笔记" --type media-note
  确认 raw/media-notes/YYYY-MM-DD-测试笔记.md 存在且有正确 frontmatter
```

---

### Phase 2: 编译引擎（7 个任务，核心）

#### Task 2.1 — API 调用封装
```
前置：Task 0.2
文件：llm-kb/tools/llm_client.py
功能：
  class LLMClient:
    def __init__(self, config: dict)
    def call(self, prompt: str, system: str = None) -> str
      - 读取 config.yaml 中的模型配置
      - 指数退避重试（retry_count 次）
      - 记录每次调用的 input/output token 数
      - 累计费用计算，超过 budget_limit_usd 时抛出 BudgetExceeded 异常
      - 返回纯文本响应
    def get_cost_summary(self) -> dict  # 返回 {calls, input_tokens, output_tokens, cost_usd}

  注意：使用 anthropic Python SDK（pip install anthropic）
  从环境变量 ANTHROPIC_API_KEY 获取密钥

验证：
  ANTHROPIC_API_KEY=sk-xxx python -c "
  from tools.llm_client import LLMClient
  import yaml
  config = yaml.safe_load(open('config.yaml'))
  client = LLMClient(config)
  resp = client.call('说 hello')
  print(resp)
  print(client.get_cost_summary())
  "
```

#### Task 2.2 — XML 响应解析器
```
前置：无
文件：llm-kb/tools/parser.py
功能：
  def parse_wiki_entries(response: str) -> list[dict]:
    """
    从 LLM 响应中解析 <wiki_entry> 标签。
    返回: [{"filename": "xxx.md", "action": "create|update", "content": "..."}]
    
    容错处理：
    - 如果 XML 格式不完整，尝试逐个 <wiki_entry> 提取
    - 如果完全无法解析，返回空列表并记录原始响应
    - 清理 content 中的多余空行（连续3个以上空行合并为2个）
    """

验证：
  python -c "
  from tools.parser import parse_wiki_entries
  test = '''
  <wiki_entry>
  <filename>Test.md</filename>
  <action>create</action>
  <content>
  # Test
  Hello world
  </content>
  </wiki_entry>
  '''
  result = parse_wiki_entries(test)
  assert len(result) == 1
  assert result[0]['filename'] == 'Test.md'
  print('PASS')
  "
```

#### Task 2.3 — 文件分段器
```
前置：无
文件：llm-kb/tools/chunker.py
功能：
  def chunk_file(filepath: str, max_size_kb: int = 50) -> list[str]:
    """
    如果文件小于 max_size_kb，返回 [整个内容]。
    如果文件大于 max_size_kb：
      1. 优先按 ## 标题分段
      2. 如果单个段仍然超大，按段落（双换行）进一步分割
      3. 每个 chunk 开头保留原文件的 frontmatter
      4. 每个 chunk 开头加注释：<!-- chunk N/M of 原文件名 -->
    返回 chunk 字符串列表。
    """

验证：
  创建一个 >50KB 的测试文件，运行 chunker，确认分段合理
```

#### Task 2.4 — 编译主引擎
```
前置：Task 2.1, 2.2, 2.3, 0.3, 0.4
文件：llm-kb/tools/compile_wiki.py
CLI 入口：
  python tools/compile_wiki.py              # 增量编译
  python tools/compile_wiki.py --full       # 全量重编译
  python tools/compile_wiki.py --dry-run    # 只显示待处理文件
  python tools/compile_wiki.py --file raw/articles/xxx.md  # 只编译指定文件

核心流程：
  1. 加载 config.yaml
  2. 初始化 StateManager，获取未处理文件列表
  3. 如果 --dry-run，打印列表并退出
  4. 对每个待处理文件：
     a. 读取文件内容
     b. 如果需要，用 chunker 分段
     c. 读取当前 INDEX.md
     d. 用 search（Task 3.1 的搜索逻辑）找到可能相关的已有条目（最多3篇）
     e. 加载 compile.txt 模板，填充占位符
     f. 调用 LLM API
     g. 解析 XML 响应
     h. 写入/更新 wiki/*.md 文件
     i. 标记文件为已处理
     j. git add + git commit -m "compile: 处理 {filename}"
     k. 打印进度：[3/15] ✓ raw/articles/xxx.md → wiki/Concept.md (+2 entries)
  5. 如果有分段文件，最后做合并编译
  6. 打印费用总结
  7. 更新 checkpoint

进度显示（用 rich）：
  ━━━━━━━━━━━━━━━━━━ 40% │ 6/15 files │ $0.42 spent │ ETA 3m

错误处理：
  - 单个文件编译失败不影响其他文件
  - 失败的文件记录到 .state/compile_errors/{filename}.txt
  - 下次运行会重试失败的文件

验证：
  1. 在 raw/articles/ 创建测试文件
  2. 运行 python tools/compile_wiki.py --dry-run，确认列出待处理文件
  3. 运行 python tools/compile_wiki.py，确认 wiki/ 下生成条目
  4. 运行 git log，确认有 commit
  5. 再次运行，确认显示"无待处理文件"
```

#### Task 2.5 — INDEX.md 生成器
```
前置：Task 0.1
文件：llm-kb/tools/indexer.py
功能：
  def regenerate_index(wiki_dir: str) -> str:
    """
    扫描 wiki/ 下所有 .md 文件（排除 INDEX.md、answers/、slides/）
    读取每篇的 frontmatter 和第一段（## 定义 下的内容）
    生成 INDEX.md：
    
    # 知识库索引
    
    最后更新：YYYY-MM-DD | 共 N 篇条目
    
    ## 条目列表
    
    | 条目 | 一句话描述 | 关联数 | 来源数 |
    |------|-----------|--------|--------|
    | [[概念A]] | 简述... | 5 | 2 |
    
    ## 按主题分类
    （根据 frontmatter 中的 related_concepts 聚类）
    """

  - 被 compile_wiki.py 在最后一步调用
  - 也可独立运行：python tools/indexer.py

验证：手动在 wiki/ 放几个 .md 文件，运行 indexer，检查 INDEX.md 格式
```

#### Task 2.6 — 合并编译（处理分段文件的最终合并）
```
前置：Task 2.4
在 compile_wiki.py 中实现（不是独立文件）

当一个大文件被分成 N 个 chunk 分别编译后：
  1. 收集所有 chunk 产生的 wiki 条目
  2. 构造合并 prompt：
     "以下条目可能有重复或不完整，请合并为最终版本：[各chunk产出]"
  3. 用合并后的版本覆盖之前的条目

验证：创建一个 >50KB 的测试文件，编译后检查 wiki 条目无重复
```

#### Task 2.7 — 编译集成测试
```
前置：Task 2.1-2.6
不产生新文件，而是运行一次端到端测试：

  1. 在 raw/articles/ 创建 test-llm-basics.md：
     ---
     source_type: article
     source_url: https://example.com/test
     clipped_at: 2025-01-01
     ---
     # LLM 基础知识
     大语言模型(LLM)是基于Transformer架构的神经网络...
     （写200字左右的测试内容，涵盖2-3个概念）

  2. 运行 python tools/compile_wiki.py
  3. 验证：
     - wiki/ 下至少生成 1 个条目 + INDEX.md
     - 条目有正确的 frontmatter
     - 条目包含 [[链接]]
     - INDEX.md 列出了所有条目
     - .state/processed_files.json 记录了测试文件
     - git log 有对应 commit

  4. 在 raw/articles/ 再创建 test-transformer.md（与上一篇相关的内容）
  5. 再次运行 compile，验证：
     - 只处理了新文件
     - 已有条目可能被 update
     - 新旧条目之间有 [[互相链接]]

如果任何步骤失败，修复后重新运行直到全部通过。
```

---

### Phase 3: 查询与输出层（5 个任务）

#### Task 3.1 — TF-IDF 搜索引擎
```
前置：Task 0.1
文件：llm-kb/tools/search.py
CLI 入口：
  python tools/search.py query "关键词"       # 全文搜索
  python tools/search.py list                  # 列出所有条目
  python tools/search.py show "条目名"         # 显示条目内容及关联
  python tools/search.py related "条目名"      # 显示关联图谱（文字版）

搜索实现：
  - 不引入外部搜索库，自己用 Python 实现简版 TF-IDF
  - 中文分词：按字符 bigram 分词（简单有效，不依赖 jieba）
  - 英文：按空格分词 + 转小写
  - 搜索范围权重：标题 x3, frontmatter x2, 正文 x1
  - 返回 top 10 结果，显示匹配片段（高亮关键词）
  
  也提供 Python API 供其他模块调用：
  def search_wiki(query: str, wiki_dir: str, top_k: int = 5) -> list[dict]:
    # 返回 [{"filename": "...", "score": 0.85, "snippet": "..."}]

  用 rich 美化 CLI 输出。

验证：
  在 wiki/ 放几个测试条目
  python tools/search.py query "测试关键词"
  确认返回相关结果，snippet 中关键词被高亮
```

#### Task 3.2 — 问答工具（含答案回流）
```
前置：Task 3.1, 2.1
文件：llm-kb/tools/ask.py
CLI 入口：
  python tools/ask.py "你的问题"
  python tools/ask.py "你的问题" --save       # 答案存入 wiki/answers/
  python tools/ask.py "你的问题" --deep       # 深度模式：先查INDEX，再逐个读链接条目

流程：
  1. 用 search_wiki() 搜索最相关的 5 篇 wiki 条目
  2. 读取这些条目的完整内容
  3. 如果 --deep：还读取这些条目中 [[链接]] 的条目（递归一层）
  4. 加载 ask.txt 模板，填充：问题 + 搜索到的条目内容
  5. 调用 LLM API
  6. 打印答案
  7. 如果 --save：
     a. 保存到 wiki/answers/YYYY-MM-DD-问题slug.md
     b. frontmatter 包含 question, sources (引用了哪些wiki条目), answered_at
     c. 这个答案文件**自动标记为已编译**（它本身就是wiki的一部分）
     d. 更新 INDEX.md
  8. 打印费用

关键设计 — 探索即积累闭环：
  --save 产生的答案文件存在 wiki/answers/ 下
  这些文件会被 search_wiki() 搜索到
  下次问相关问题时，之前的答案会作为上下文提供给 LLM
  → 知识库越用越智能

验证：
  python tools/ask.py "什么是 Transformer?" --save
  确认答案打印正确
  确认 wiki/answers/ 下生成了文件
  再次运行 python tools/search.py query "Transformer"
  确认答案文件出现在搜索结果中
```

#### Task 3.3 — Marp 幻灯片生成
```
前置：Task 3.1, 2.1
文件：llm-kb/tools/slides.py
CLI 入口：
  python tools/slides.py "主题关键词"

流程：
  1. 搜索相关 wiki 条目
  2. 让 LLM 整理为 Marp 格式幻灯片
  3. 保存到 wiki/slides/YYYY-MM-DD-主题.md
  4. 提示用户可用 Obsidian Marp 插件预览

验证：运行一次，确认输出文件是合法 Marp 格式
```

#### Task 3.4 — 导出报告
```
前置：Task 3.1, 2.1
文件：llm-kb/tools/report.py
CLI 入口：
  python tools/report.py "主题" --format md     # Markdown 报告
  python tools/report.py "主题" --format brief  # 一段话摘要

流程类似 ask.py，但 prompt 模板不同：
  - md 格式：生成带标题/子标题/引用的完整报告
  - brief 格式：只要一段 200 字以内的摘要

输出保存到 wiki/answers/YYYY-MM-DD-report-主题.md

验证：运行一次，确认报告格式正确
```

#### Task 3.5 — 查询层集成测试
```
前置：Task 3.1-3.4
运行端到端验证（要求 Phase 2 的测试数据存在）：
  1. python tools/search.py list → 应列出已有条目
  2. python tools/search.py query "LLM" → 应返回结果
  3. python tools/ask.py "什么是LLM?" --save → 应生成答案
  4. python tools/search.py query "LLM" → 答案文件应出现在结果中
  5. python tools/slides.py "LLM" → 应生成幻灯片
```

---

### Phase 4: 健康维护（4 个任务）

#### Task 4.1 — 本地 Lint 检查
```
前置：Task 0.1
文件：llm-kb/tools/lint.py
CLI 入口：
  python tools/lint.py                # 只报告
  python tools/lint.py --fix          # 自动修复本地可修复的问题
  python tools/lint.py --ai-fix      # 调用 LLM 修复复杂问题
  python tools/lint.py --dry-run     # 列出将修复什么但不执行

检查项（本地，不调API）：
  1. 断链：[[xxx]] 指向不存在的 wiki/xxx.md
  2. 孤立条目：没有任何条目 [[链接]] 到它
  3. 缺失 frontmatter 或字段不完整
  4. INDEX.md 与实际文件不同步
  5. 空条目（< min_entry_length 字）
  6. 重复条目（文件名相似度 > 80%，如 LLM.md 和 Large-Language-Model.md）

--fix 自动修复：
  - 断链 → 创建 stub 条目（只有标题和"待编译"标记）
  - INDEX 不同步 → 调用 indexer.py 重新生成
  - 缺失字段 → 补充默认值

输出用 rich 表格，每行：类型 | 位置 | 详情 | 状态(发现/已修复/需人工)

验证：
  手动在 wiki/ 中制造一个断链，运行 lint，确认检出
  运行 lint --fix，确认修复
```

#### Task 4.2 — AI Lint 修复
```
前置：Task 4.1, 2.1
在 lint.py 的 --ai-fix 模式中实现：

  对于本地无法修复的问题（如"内容矛盾"、"缺失关联"）：
  1. 收集所有需要 AI 修复的问题
  2. 将相关条目内容 + 问题描述发给 LLM
  3. LLM 返回修复后的条目内容
  4. 写入修复结果
  5. git commit

prompt 模板：templates/lint_ai.txt

验证：创建两个内容矛盾的条目，运行 --ai-fix，确认矛盾被解决
```

#### Task 4.3 — 知识探索建议
```
前置：Task 4.1, 2.1
文件：llm-kb/tools/explore.py
CLI 入口：
  python tools/explore.py

功能：
  1. 读取所有 wiki 条目
  2. 调用 LLM，prompt：
     "分析这个知识库的覆盖范围，建议 5 个值得深入研究的方向，
      以及 5 个当前知识库中有提及但尚未独立成篇的概念"
  3. 输出建议列表
  4. 可选：--add 自动为建议的概念创建 stub 条目

验证：运行一次，确认输出的建议合理
```

#### Task 4.4 — 统计仪表盘
```
前置：Task 0.4
文件：llm-kb/tools/stats.py
CLI 入口：
  python tools/stats.py

输出（用 rich panel）：
  ╭──────────── 知识库统计 ─────────────╮
  │ Raw 文件:    45  (articles: 30, papers: 10, repos: 5)
  │ Wiki 条目:   62  (avg 850 字/篇)
  │ 答案记录:    18
  │ 幻灯片:      3
  │ 内部链接:    234 (avg 3.8/篇)
  │ 断链:        2
  │ 孤立条目:    4
  │ 待处理:      3 个 raw 文件
  │ 累计API费用: $2.35 (来自 compile_log)
  ╰─────────────────────────────────────╯

验证：运行，确认数字与实际一致
```

---

### Phase 5: 统一入口 + 文档（5 个任务）

#### Task 5.1 — Makefile
```
前置：所有 Phase 0-4 完成
文件：llm-kb/Makefile

目标：
  init        安装依赖
  extract     PDF → Markdown
  clip        网页抓取 (URL=xxx)
  note        新建笔记 (TITLE=xxx TYPE=xxx)
  compile     增量编译
  compile-full 全量重编译
  search      搜索 (Q=xxx)
  ask         问答 (Q=xxx)
  ask-save    问答并保存 (Q=xxx)
  slides      生成幻灯片 (TOPIC=xxx)
  report      生成报告 (TOPIC=xxx)
  lint        健康检查
  lint-fix    自动修复
  lint-ai     AI修复
  explore     探索建议
  stats       统计
  status      快速状态（待处理数、条目数）
  help        帮助

每个目标用 ## 注释，make help 自动提取显示。

验证：make help 输出所有命令及说明
```

#### Task 5.2 — README.md
```
前置：Task 5.1
文件：llm-kb/README.md

内容结构：
  1. 项目简介（一段话 + 方法论来源引用 Karpathy）
  2. 快速开始（5步：clone → make init → 放文件 → make compile → make search）
  3. 完整命令参考（每个 make target 的用法和示例）
  4. 目录结构说明
  5. 配置说明（config.yaml 各字段含义）
  6. 与 Obsidian 配合使用
  7. 费用估算（大约多少文件花多少钱）
  8. FAQ

验证：通读 README，确认一个新用户能照着做
```

#### Task 5.3 — 初始化脚本
```
前置：Task 5.1
文件：llm-kb/tools/init_project.py
功能：
  make init 时调用
  - 检查 Python 版本 >= 3.10
  - pip install -r requirements.txt
  - 创建所有必要目录
  - 初始化 .state/ 文件
  - 检查 ANTHROPIC_API_KEY 是否设置
  - 初始化 git 仓库（如果尚未初始化）
  - 打印欢迎信息和下一步指引

验证：在空目录运行 make init，确认一切就绪
```

#### Task 5.4 — 全流程端到端测试
```
前置：所有任务完成
这不是一个代码任务，而是验证任务：

  1. 删除所有测试数据（rm -rf raw/* wiki/* .state/*）
  2. make init
  3. 创建 3 个测试 raw 文件（手写或让 LLM 生成一些技术笔记）
  4. make compile → 确认 wiki/ 下生成条目
  5. make search Q="关键词" → 确认搜索有结果
  6. make ask-save Q="问一个问题" → 确认答案保存
  7. make search Q="刚才问题的关键词" → 确认答案出现在搜索中
  8. make lint → 确认无严重问题
  9. make stats → 确认统计正确
  10. 再添加 2 个 raw 文件 → make compile → 确认增量编译
  11. make explore → 确认建议输出

全部通过后，最终 git commit -m "project: complete and tested"
```

#### Task 5.5 — 清理与交付
```
前置：Task 5.4
  1. 删除所有测试数据（保留工具代码）
  2. 确保 .gitignore 正确
  3. 确保所有 Python 文件有 docstring
  4. 确保所有 CLI 工具有 --help
  5. git tag v1.0
  6. 打印最终目录结构
```

---

## 五、中断恢复指南

如果 Claude Code 中途中断，用以下 prompt 继续：

```
继续执行 LLM Knowledge Base 项目。

1. 读取 .state/checkpoints.json 查看完成进度
2. 读取项目根目录的 Makefile 和现有代码了解当前状态
3. 找到第一个未完成的 Task，从那里继续
4. 保持之前的代码风格和架构一致

项目计划在 PROJECT_PLAN.md 中（就是这个文件），按 Task 编号顺序执行。
```

每个 Task 完成后必须：
1. 运行该 Task 的验证步骤
2. git commit
3. 更新 .state/checkpoints.json

---

## 六、注意事项

1. **所有 Python 文件开头**加 `#!/usr/bin/env python3` 和 `# -*- coding: utf-8 -*-`
2. **不要用 f-string 做 prompt 模板**，用 str.format() 或 string.Template，避免大括号冲突
3. **每个 API 调用都要 try-except**，失败不能中断整个流程
4. **git commit message 格式**：`类型: 描述`，类型为 init/feat/fix/test/docs
5. **中文文件名**：wiki 条目用中文名（如 `大语言模型.md`），搜索和链接都支持中文
6. **requirements.txt 不要加太多依赖**，尽量用标准库。核心依赖只有：anthropic, pymupdf, pyyaml, rich, click
