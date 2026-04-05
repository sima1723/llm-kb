# LLM 知识库 — 完整部署指南（小白版）

> 适用系统：**macOS** 和 **Linux（Ubuntu/Debian/Arch 等）**  
> 预计耗时：15 分钟  
> 需要注册：**Anthropic 账号**（付费 API，按使用量计费，非常便宜）

---

## 目录

1. [需要注册什么账号？](#1-需要注册什么账号)
2. [系统环境准备](#2-系统环境准备)
3. [获取代码](#3-获取代码)
4. [配置 API Key](#4-配置-api-key)
5. [安装依赖并初始化](#5-安装依赖并初始化)
6. [验证安装](#6-验证安装)
7. [第一次使用](#7-第一次使用)
8. [常用命令速查](#8-常用命令速查)
9. [费用说明](#9-费用说明)
10. [常见问题 FAQ](#10-常见问题-faq)

---

## 1. 需要注册什么账号？

### 只需要一个账号：Anthropic

| 项目 | 说明 |
|------|------|
| 注册地址 | https://console.anthropic.com |
| 费用模式 | 按实际使用量付费（非订阅），无月费 |
| 首充建议 | $5 够用很久（编译一篇文章约 $0.05） |
| 支付方式 | 信用卡 / 借记卡（国内 Visa/MasterCard 一般可用） |

### 注册步骤

1. 打开 https://console.anthropic.com
2. 点击 **Sign Up**，用邮箱注册
3. 验证邮箱
4. 登录后，左侧菜单点击 **"API Keys"**
5. 点击 **"Create Key"**，输入一个名字（随便取，比如 `my-kb`）
6. 复制生成的 Key（格式是 `sk-ant-api03-...`）

   > **重要**：Key 只显示一次，请立刻复制并保存好！

7. 点击左侧 **"Billing"** → **"Add credit"** → 充值（建议先充 $5-10）

---

## 2. 系统环境准备

### 检查 Python 版本（需要 3.10 及以上）

```bash
python3 --version
```

如果显示 `Python 3.10.x` 或更高版本，跳到下一步。

---

#### macOS — 安装 Python

**方法一（推荐）：使用 Homebrew**

```bash
# 1. 安装 Homebrew（如果没有）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安装 Python
brew install python@3.11

# 3. 验证
python3 --version
```

**方法二：直接下载安装包**

- 前往 https://www.python.org/downloads/
- 下载 macOS 的最新版本（3.11 或 3.12）
- 双击 `.pkg` 文件安装

---

#### Linux（Ubuntu / Debian）— 安装 Python

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
python3 --version
```

#### Linux（Arch / Manjaro）

```bash
sudo pacman -Syu python python-pip
python3 --version
```

---

### 检查 make 和 git

```bash
make --version
git --version
```

macOS 如果没有 make：
```bash
xcode-select --install
```

Linux 如果没有 make：
```bash
sudo apt install make git -y   # Ubuntu/Debian
# 或
sudo pacman -S make git        # Arch
```

---

## 3. 获取代码

### 方式一：如果你已经有这个代码文件夹

```bash
# 进入项目目录（替换为你的实际路径）
cd /path/to/llm-kb
```

### 方式二：从 Git 仓库克隆

```bash
git clone <仓库地址> llm-kb
cd llm-kb
```

### 确认目录结构正确

```bash
ls
```

应该能看到：`config.yaml`、`Makefile`、`requirements.txt`、`tools/`、`raw/`、`wiki/` 等。

---

## 4. 配置 API Key

**这是最关键的一步。** 打开项目根目录的 `config.yaml` 文件：

```bash
# 用你熟悉的编辑器打开，任选一种：
nano config.yaml          # 终端内编辑（推荐小白）
code config.yaml          # VS Code
open -a TextEdit config.yaml  # macOS 文本编辑器
```

找到文件最顶部的这两行：

```yaml
api_key: ""
base_url: ""
```

---

### 方式 A：使用 Anthropic 官方 API（国际版）

只需填 `api_key`，`base_url` 留空：

```yaml
api_key: "sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxx"
base_url: ""
```

---

### 方式 B：使用中转/代理服务（推荐国内用户）

支持 **AnyRouter**、**OpenRouter** 等兼容 Anthropic API 的中转服务，填入中转地址和对应 Key：

```yaml
api_key: "你的中转服务 Key"
base_url: "https://api.anyruter.com"   # 替换为你的中转服务地址
```

> 中转服务通常在其控制台提供 `Base URL` 和 `API Key`，照填即可。  
> 也支持通过环境变量设置：`ANTHROPIC_API_KEY` 和 `ANTHROPIC_BASE_URL`。

---

保存文件（nano 用 `Ctrl+O` 然后 `Enter`，再 `Ctrl+X` 退出）。

> **安全提示**：`config.yaml` 已在 `.gitignore` 中（建议检查一下），不会被意外上传到 GitHub。

---

## 5. 安装依赖并初始化

在项目目录下运行：

```bash
make init
```

这个命令会自动：
- 检查 Python 版本是否满足要求
- 安装所有 Python 依赖（anthropic、pymupdf、pyyaml、rich、click）
- 创建必要的目录结构（`raw/`、`wiki/`、`.state/` 等）
- 验证 API Key 是否有效

安装过程大约 1-2 分钟，看到类似下面的输出说明成功：

```
✅ Python 3.11.x — 版本满足要求
✅ 依赖安装完成
✅ 目录结构已创建
✅ API Key 验证通过
🎉 初始化完成！
```

---

### 如果 make init 出错了怎么办？

#### 错误：`pip: command not found`

```bash
# macOS
brew install python@3.11

# Linux
sudo apt install python3-pip -y
```

#### 错误：`anthropic` 安装失败

手动安装：

```bash
pip3 install -r requirements.txt
```

或使用虚拟环境（更干净）：

```bash
python3 -m venv venv
source venv/bin/activate      # macOS/Linux
pip install -r requirements.txt
```

> 使用虚拟环境后，每次打开新终端都需要先运行 `source venv/bin/activate`

#### 错误：API Key 无效

- 确认 `config.yaml` 中的 Key 没有多余空格
- 确认 Anthropic 账户已充值
- 在 https://console.anthropic.com/api-keys 检查 Key 是否仍然有效

---

## 6. 验证安装

运行以下命令确认一切正常：

```bash
# 查看帮助（不需要 API，立即返回）
make help

# 查看统计仪表盘（不需要 API）
make stats

# 查看当前状态
make status
```

---

## 7. 第一次使用

### 步骤一：放入原始资料

**方式 A：抓取网页文章**

```bash
make clip URL=https://example.com/some-article
```

**方式 B：添加 PDF 论文**

把 PDF 文件复制到 `raw/papers/` 目录，然后：

```bash
make extract
```

**方式 C：手动写笔记**

```bash
make note TITLE="我的第一篇笔记" TYPE=article
```

然后编辑 `raw/articles/我的第一篇笔记.md`，在 `---` 分隔符下方填写内容。

**方式 D：直接放 Markdown 文件**

把 `.md` 文件直接复制到 `raw/articles/` 目录即可。

---

### 步骤二：编译成知识库

```bash
make compile
```

这会调用 Claude AI，把你的原始资料编译成结构化的 wiki 条目。  
**这一步会消耗 API 费用**（每篇文章约 $0.05）。

编译完成后，`wiki/` 目录会生成 `.md` 文件。

---

### 步骤三：搜索和提问

```bash
# 搜索关键词
make search Q="人工智能"

# 问问题（不保存）
make ask Q="什么是大语言模型？"

# 问问题并保存答案（推荐，答案会回流到知识库）
make ask-save Q="Transformer 的核心原理是什么？"

# 列出所有知识库条目
make list
```

---

## 8. 常用命令速查

### 数据摄入

```bash
make clip URL=<网址>                    # 抓取网页
make extract PDF=<PDF路径>             # 提取PDF
make note TITLE="标题" TYPE=article    # 新建笔记
```

### 编译知识库

```bash
make compile                           # 增量编译（只处理新文件，推荐）
make compile-full                      # 全量重编译
make compile-dry                       # 预览待处理文件（不花钱）
```

### 搜索与问答

```bash
make search Q="关键词"
make list
make show Q="条目名"
make ask Q="你的问题"
make ask-save Q="你的问题"             # 问答 + 保存答案（推荐）
make ask-deep Q="复杂问题"             # 深度问答（读取关联条目）
```

### 导出

```bash
make slides TOPIC="主题"               # 生成 Marp 幻灯片
make report TOPIC="主题"               # 生成完整 Markdown 报告
make brief TOPIC="主题"                # 生成一段话摘要
```

### 维护

```bash
make lint                              # 健康检查（断链/孤立条目）
make lint-fix                          # 自动修复可修复问题
make lint-ai                           # 调用 AI 修复复杂问题
make explore                           # 推荐知识探索方向
make stats                             # 统计仪表盘
make status                            # 快速状态
```

---

## 9. 费用说明

| 操作 | 约花费 |
|------|--------|
| 编译 1 篇文章（~2000字） | ~$0.05 |
| 编译 10 篇文章 | ~$0.30–0.80 |
| 编译 50 篇文章 | ~$2–5 |
| 一次问答 | ~$0.01–0.03 |
| 生成幻灯片 | ~$0.03–0.05 |

### 费用保护

`config.yaml` 中的 `budget_limit_usd: 5.0` 是单次编译的费用上限。  
超出后系统会报错停止，不会继续消费。可以根据需要调整。

### 查看已花费

```bash
make stats
```

会显示总 API 调用次数和累计费用。

---

## 10. 常见问题 FAQ

**Q：运行 `make` 提示 `command not found`**  
A：macOS 运行 `xcode-select --install`；Linux 运行 `sudo apt install make -y`

**Q：`python3: command not found`**  
A：按照第 2 节安装 Python。macOS 用户也可以试试 `python` 代替 `python3`。

**Q：API 调用报错 `AuthenticationError`**  
A：检查 `config.yaml` 中的 `api_key` 是否填写正确，没有多余的空格或引号。

**Q：API 调用报错 `402 Payment Required`**  
A：Anthropic 账户余额不足，前往 https://console.anthropic.com/billing 充值。

**Q：编译一直卡住或超时**  
A：可能是网络问题（需要访问 Anthropic API）。系统有自动重试机制，等待几分钟。如果持续失败，检查网络是否能访问 `api.anthropic.com`。

**Q：在国内使用需要代理吗？**  
A：Anthropic API 在国内大陆地区可能需要代理。可以设置：
```bash
export https_proxy=http://127.0.0.1:7890  # 替换为你的代理地址
make compile
```
或者把代理地址添加到 shell 配置文件（`~/.bashrc` 或 `~/.zshrc`）中永久生效。

**Q：`make compile` 之后 wiki/ 目录是空的**  
A：先确认 `raw/` 目录下有文件。运行 `make status` 查看待处理文件数量。

**Q：能用中文提问吗？**  
A：完全支持，直接中文提问即可：`make ask Q="什么是注意力机制"`

**Q：wiki 条目文件在哪里，能手动编辑吗？**  
A：在 `wiki/` 目录，普通 Markdown 文件，可以用任何文本编辑器或 Obsidian 查看。但建议不要手动编辑——下次编译可能覆盖你的修改。如果需要修改，修改 `raw/` 中的源文件，再重新编译。

**Q：可以配合 Obsidian 使用吗？**  
A：可以。在 Obsidian 中打开 `wiki/` 目录，`[[链接]]` 会自动渲染为双向链接图谱。

---

## 快速上手总结（3 步）

```bash
# 第一步：配置 API Key（只需做一次）
nano config.yaml   # 把 api_key 填上

# 第二步：安装（只需做一次）
make init

# 第三步：日常使用
make clip URL=https://...    # 放入资料
make compile                  # 编译
make ask-save Q="你的问题"   # 提问
```

---

*如遇问题请查看 `.state/compile_errors/` 目录下的错误日志，或重新运行 `make init` 诊断环境。*
