# LLM Knowledge Base — Makefile
# 用法: make help

PYTHON := python3
TOOLS  := tools

.PHONY: help init extract clip note compile compile-full \
        search ask ask-save slides report lint lint-fix lint-ai \
        explore explore-add stub-fill stub-fill-dry stats status

## help: 显示帮助信息
help:
	@echo ""
	@echo "LLM Knowledge Base — 命令列表"
	@echo "────────────────────────────────────────────────────────"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /'
	@echo "────────────────────────────────────────────────────────"
	@echo ""

## init: 安装依赖并初始化项目
init:
	$(PYTHON) $(TOOLS)/init_project.py

## extract: 将 raw/papers/ 中的 PDF 转为 Markdown  (PDF=路径，可选)
extract:
	@if [ -n "$(PDF)" ]; then \
		$(PYTHON) $(TOOLS)/pdf_to_md.py "$(PDF)"; \
	else \
		$(PYTHON) $(TOOLS)/pdf_to_md.py raw/papers/; \
	fi

## clip: 抓取网页到 raw/articles/  (URL=https://...)
clip:
	@if [ -z "$(URL)" ]; then echo "请指定 URL，例如: make clip URL=https://example.com"; exit 1; fi
	$(PYTHON) $(TOOLS)/web_to_md.py "$(URL)"

## note: 新建手动笔记  (TITLE=标题  TYPE=article|paper|media-note)
note:
	@if [ -z "$(TITLE)" ]; then echo "请指定 TITLE，例如: make note TITLE='我的笔记'"; exit 1; fi
	$(PYTHON) $(TOOLS)/new_note.py "$(TITLE)" --type $(or $(TYPE),article)

## compile: 增量编译（只处理新增/修改的文件）
compile:
	$(PYTHON) $(TOOLS)/compile_wiki.py

## compile-full: 全量重编译（重新处理所有 raw 文件）
compile-full:
	$(PYTHON) $(TOOLS)/compile_wiki.py --full

## compile-dry: 预览待处理文件（不实际编译）
compile-dry:
	$(PYTHON) $(TOOLS)/compile_wiki.py --dry-run

## search: 全文搜索  (Q=关键词)
search:
	@if [ -z "$(Q)" ]; then echo "请指定 Q，例如: make search Q='Transformer'"; exit 1; fi
	$(PYTHON) $(TOOLS)/search.py query "$(Q)"

## list: 列出所有 wiki 条目
list:
	$(PYTHON) $(TOOLS)/search.py list

## show: 显示条目详情  (Q=条目名)
show:
	@if [ -z "$(Q)" ]; then echo "请指定 Q，例如: make show Q='注意力机制'"; exit 1; fi
	$(PYTHON) $(TOOLS)/search.py show "$(Q)"

## ask: 问答（不保存）  (Q=问题)
ask:
	@if [ -z "$(Q)" ]; then echo "请指定 Q，例如: make ask Q='什么是LLM?'"; exit 1; fi
	$(PYTHON) $(TOOLS)/ask.py "$(Q)"

## ask-save: 问答并保存答案到 wiki/answers/  (Q=问题)
ask-save:
	@if [ -z "$(Q)" ]; then echo "请指定 Q，例如: make ask-save Q='什么是LLM?'"; exit 1; fi
	$(PYTHON) $(TOOLS)/ask.py "$(Q)" --save

## ask-deep: 深度问答（递归读取关联条目）  (Q=问题)
ask-deep:
	@if [ -z "$(Q)" ]; then echo "请指定 Q"; exit 1; fi
	$(PYTHON) $(TOOLS)/ask.py "$(Q)" --deep --save

## slides: 生成 Marp 幻灯片  (TOPIC=主题)
slides:
	@if [ -z "$(TOPIC)" ]; then echo "请指定 TOPIC，例如: make slides TOPIC='Transformer'"; exit 1; fi
	$(PYTHON) $(TOOLS)/slides.py "$(TOPIC)"

## report: 生成完整报告  (TOPIC=主题)
report:
	@if [ -z "$(TOPIC)" ]; then echo "请指定 TOPIC，例如: make report TOPIC='LLM'"; exit 1; fi
	$(PYTHON) $(TOOLS)/report.py "$(TOPIC)" --format md

## brief: 生成一段话摘要  (TOPIC=主题)
brief:
	@if [ -z "$(TOPIC)" ]; then echo "请指定 TOPIC"; exit 1; fi
	$(PYTHON) $(TOOLS)/report.py "$(TOPIC)" --format brief

## lint: 健康检查（只报告）
lint:
	$(PYTHON) $(TOOLS)/lint.py

## lint-fix: 自动修复本地可修复的问题
lint-fix:
	$(PYTHON) $(TOOLS)/lint.py --fix

## lint-ai: 调用 AI 修复复杂问题
lint-ai:
	$(PYTHON) $(TOOLS)/lint.py --ai-fix

## explore: 知识探索建议
explore:
	$(PYTHON) $(TOOLS)/explore.py

## explore-add: 探索建议并自动创建 stub 条目
explore-add:
	$(PYTHON) $(TOOLS)/explore.py --add

## stub-fill: 用 LLM 填充所有"待补充"stub 条目  (ENTRY=条目名，可选)
stub-fill:
	@if [ -n "$(ENTRY)" ]; then \
		$(PYTHON) $(TOOLS)/stub_fill.py --entry "$(ENTRY)"; \
	else \
		$(PYTHON) $(TOOLS)/stub_fill.py; \
	fi

## stub-fill-dry: 预览待填充 stub 列表（不调用 API）
stub-fill-dry:
	$(PYTHON) $(TOOLS)/stub_fill.py --dry-run

## stats: 统计仪表盘
stats:
	$(PYTHON) $(TOOLS)/stats.py

## status: 快速状态（待处理数 + 条目数）
status:
	@$(PYTHON) -c "\
import sys; sys.path.insert(0, '.'); \
from tools.stats import count_raw_files, count_wiki_entries, count_pending_raw; \
r = count_raw_files(); w = count_wiki_entries(); p = count_pending_raw(); \
print(f'待处理: {p} 个 raw 文件  |  Wiki 条目: {w[\"total\"]} 篇  |  答案: {w[\"answers\"]} 条')"
