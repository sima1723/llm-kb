#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Marp 幻灯片生成器 — 基于 wiki 知识库生成 Marp 格式演示文稿。

CLI:
  python tools/slides.py "主题关键词"
  python tools/slides.py "主题关键词" --open    # 生成后尝试打开文件
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import yaml

try:
    from rich.console import Console
    from rich.panel import Panel
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from tools.search import search_wiki
from tools.llm_client import LLMClient
from tools.ask import _truncate_entry

console = Console() if HAS_RICH else None

WIKI_DIR = _HERE / "wiki"
SLIDES_DIR = WIKI_DIR / "slides"
CONFIG_FILE = _HERE / "config.yaml"

_SLIDES_PROMPT = """\
你是一位技术演讲者。请根据以下知识库条目，生成一份关于"{topic}"的 Marp 格式幻灯片。语言：{language}

<wiki_entries>
{wiki_entries}
</wiki_entries>

## Marp 幻灯片要求
1. 开头必须包含 Marp frontmatter（如下），不要遗漏
2. 每张幻灯片用 `---` 分隔
3. 共 6-10 张幻灯片，结构为：标题页 → 目录 → 正文（每个要点一张）→ 总结 → 参考资料
4. 每张幻灯片内容简洁，要点不超过 5 条
5. 用 [[链接]] 格式引用相关 wiki 条目
6. 参考资料页列出所用知识库条目

## Marp Frontmatter 模板（必须完整输出）
---
marp: true
theme: default
paginate: true
header: "LLM 知识库"
footer: "由 llm-kb 自动生成"
---

现在直接输出完整的幻灯片 Markdown，从 frontmatter 开始：
"""


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def _slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r'[^\w\u4e00-\u9fff]', '-', text)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:max_len]


@click.command()
@click.argument("topic")
@click.option("--top-k", default=6, show_default=True, help="参考条目数量")
@click.option("--wiki-dir", default=None, help="wiki 目录路径")
def main(topic: str, top_k: int, wiki_dir: Optional[str]):
    """生成 Marp 格式幻灯片"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR
    config = _load_config()
    language = config.get("wiki", {}).get("language", "zh")

    # 搜索相关条目
    if HAS_RICH:
        with console.status(f"[cyan]搜索「{topic}」相关条目...[/cyan]"):
            results = search_wiki(topic, str(wd), top_k=top_k)
    else:
        print(f"搜索「{topic}」相关条目...")
        results = search_wiki(topic, str(wd), top_k=top_k)

    if not results:
        msg = "未找到相关条目，请先编译知识库"
        if HAS_RICH:
            console.print(f"[yellow]{msg}[/yellow]")
        else:
            print(msg)
        return

    # 幻灯片只需高层概述，每个条目截断到 1500 字符
    MAX_CHARS = 1500
    entries_text = []
    for r in results:
        fp = Path(r["filepath"])
        if fp.exists():
            content = _truncate_entry(fp.read_text(encoding="utf-8", errors="ignore"), MAX_CHARS)
            entries_text.append(f"=== {r['filename']} ===\n{content}")

    wiki_entries = "\n\n".join(entries_text)

    # 构建 prompt
    prompt = _SLIDES_PROMPT.format(
        topic=topic,
        language=language,
        wiki_entries=wiki_entries,
    )

    # 调用 LLM
    client = LLMClient(config, tool="slides")
    slides_max_tokens = config.get("llm", {}).get("max_tokens_by_tool", {}).get("slides")
    if HAS_RICH:
        with console.status("[cyan]正在生成幻灯片...[/cyan]"):
            slides_content = client.call(prompt, max_tokens=slides_max_tokens)
    else:
        print("正在生成幻灯片...")
        slides_content = client.call(prompt, max_tokens=slides_max_tokens)

    # 确保 marp: true frontmatter 存在
    if "marp: true" not in slides_content:
        slides_content = "---\nmarp: true\ntheme: default\npaginate: true\n---\n\n" + slides_content

    # 保存到 wiki/slides/
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    slug = _slug(topic)
    filename = f"{today}-{slug}.md"
    filepath = SLIDES_DIR / filename

    filepath.write_text(slides_content, encoding="utf-8")

    # 费用
    summary = client.get_cost_summary()

    if HAS_RICH:
        console.print(f"\n[green]幻灯片已保存: wiki/slides/{filename}[/green]")
        console.print(f"[dim]费用: ${summary['cost_usd']:.4f}  |  可用 Obsidian Marp 插件预览[/dim]")
        # 预览前几行
        preview = "\n".join(slides_content.split("\n")[:20])
        console.print(Panel(preview, title="[bold]预览（前20行）[/bold]", border_style="dim"))
    else:
        print(f"\n幻灯片已保存: wiki/slides/{filename}")
        print(f"费用: ${summary['cost_usd']:.4f}")
        print("可用 Obsidian Marp 插件预览")


if __name__ == "__main__":
    main()
