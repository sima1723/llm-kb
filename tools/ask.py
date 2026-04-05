#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
问答工具 — 基于 wiki 知识库回答问题，支持答案回流保存。

CLI:
  python tools/ask.py "你的问题"
  python tools/ask.py "你的问题" --save       # 答案存入 wiki/answers/
  python tools/ask.py "你的问题" --deep       # 深度模式：递归读取链接条目
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
    from rich.markdown import Markdown
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ─── 路径 ──────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from tools.search import search_wiki
from tools.llm_client import LLMClient
from tools.indexer import regenerate_index

console = Console() if HAS_RICH else None

WIKI_DIR = _HERE / "wiki"
ANSWERS_DIR = WIKI_DIR / "answers"
TEMPLATES_DIR = _HERE / "templates"
CONFIG_FILE = _HERE / "config.yaml"


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def _slug(text: str, max_len: int = 50) -> str:
    """生成文件名友好的 slug"""
    # 保留中文、字母、数字
    slug = re.sub(r'[^\w\u4e00-\u9fff]', '-', text)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:max_len]


def _read_entry(filepath: Path) -> str:
    """读取条目内容"""
    try:
        return filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_links(content: str) -> list[str]:
    """提取 [[链接]] 中的条目名"""
    return re.findall(r'\[\[(.+?)\]\]', content)


def _truncate_entry(content: str, max_chars: int) -> str:
    """
    截断条目内容，优先在段落边界（双换行）处断开，
    避免 LLM 读到半截句子。丢弃"## 来源"之后的内容（最不重要）。
    """
    if len(content) <= max_chars:
        return content
    # 先尝试去掉"来源"节以减小体积
    source_idx = content.find("\n## 来源")
    if source_idx != -1 and source_idx > max_chars // 2:
        content = content[:source_idx]
    if len(content) <= max_chars:
        return content
    # 在 max_chars 附近找最近的段落分隔（双换行）
    cut = content.rfind("\n\n", 0, max_chars)
    return content[:cut] if cut > max_chars // 2 else content[:max_chars]



    """
    构建问答上下文：搜索相关 wiki 条目，deep 模式下递归读取一层链接。
    返回 (context_text, source_files)
    """
    results = search_wiki(question, str(wiki_dir), top_k=top_k)
    if not results:
        return "", []

    # 每个条目最多发送 2000 字符，足够 LLM 理解内容，避免长文档浪费 token
    MAX_CHARS = 2000

    loaded_files: dict[str, str] = {}  # filename -> content

    # 加载直接搜索结果
    for r in results:
        fp = Path(r["filepath"])
        if fp.exists():
            loaded_files[r["filename"]] = _truncate_entry(_read_entry(fp), MAX_CHARS)

    # deep 模式：递归一层链接
    if deep:
        extra: dict[str, str] = {}
        for fname, content in list(loaded_files.items()):
            links = _extract_links(content)
            for lk in links:
                lk_path = wiki_dir / f"{lk}.md"
                lk_rel = f"{lk}.md"
                if lk_rel not in loaded_files and lk_rel not in extra and lk_path.exists():
                    extra[lk_rel] = _truncate_entry(_read_entry(lk_path), MAX_CHARS)
        loaded_files.update(extra)

    context_text = "\n\n".join(
        f"=== {fname} ===\n{content}" for fname, content in loaded_files.items()
    )
    return context_text, list(loaded_files.keys())


@click.command()
@click.argument("question")
@click.option("--save", is_flag=True, help="将答案保存到 wiki/answers/")
@click.option("--deep", is_flag=True, help="深度模式：递归读取链接条目")
@click.option("--wiki-dir", default=None, help="wiki 目录路径")
def main(question: str, save: bool, deep: bool, wiki_dir: Optional[str]):
    """基于知识库回答问题"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR
    config = _load_config()
    language = config.get("wiki", {}).get("language", "zh")

    # 1. 构建上下文
    if HAS_RICH:
        with console.status("[cyan]正在搜索相关条目...[/cyan]"):
            context_text, source_files = build_context(question, wd, deep=deep)
    else:
        print("正在搜索相关条目...")
        context_text, source_files = build_context(question, wd, deep=deep)

    if not context_text:
        msg = "知识库为空或未找到相关条目，请先运行 compile_wiki.py"
        if HAS_RICH:
            console.print(f"[yellow]{msg}[/yellow]")
        else:
            print(msg)
        context_text = "（知识库为空）"

    # 2. 加载 prompt 模板
    ask_template_path = TEMPLATES_DIR / "ask.txt"
    if ask_template_path.exists():
        template = ask_template_path.read_text(encoding="utf-8")
    else:
        template = (
            "你是一位知识库助手。语言：{language}\n\n"
            "<wiki_entries>\n{wiki_entries}\n</wiki_entries>\n\n"
            "问题：{question}\n\n请回答："
        )

    prompt = template.format(
        language=language,
        wiki_entries=context_text,
        question=question,
    )

    # 3. 调用 LLM
    try:
        client = LLMClient(config)
    except Exception as e:
        print(f"初始化 LLM 客户端失败: {e}")
        sys.exit(1)

    ask_max_tokens = config.get("llm", {}).get("max_tokens_by_tool", {}).get("ask")
    if HAS_RICH:
        with console.status("[cyan]正在生成答案...[/cyan]"):
            answer = client.call(prompt, max_tokens=ask_max_tokens)
    else:
        print("正在生成答案...")
        answer = client.call(prompt, max_tokens=ask_max_tokens)

    # 4. 打印答案
    if HAS_RICH:
        console.print()
        console.print(Panel(
            Markdown(answer),
            title=f"[bold cyan]Q: {question[:60]}[/bold cyan]",
            border_style="cyan",
        ))
    else:
        print(f"\n{'='*60}")
        print(f"Q: {question}")
        print(f"{'='*60}")
        print(answer)
        print(f"{'='*60}\n")

    # 5. 打印费用
    summary = client.get_cost_summary()
    cost_msg = (
        f"费用: ${summary['cost_usd']:.4f}  "
        f"(输入 {summary['input_tokens']} tokens, 输出 {summary['output_tokens']} tokens)"
    )
    if HAS_RICH:
        console.print(f"[dim]{cost_msg}[/dim]")
    else:
        print(cost_msg)

    # 6. 保存答案（--save 模式）
    if save:
        _save_answer(question, answer, source_files, wd)


def _save_answer(question: str, answer: str, source_files: list[str], wiki_dir: Path):
    """保存答案到 wiki/answers/，并更新 INDEX.md"""
    answers_dir = wiki_dir / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    slug = _slug(question)
    filename = f"{today}-{slug}.md"
    filepath = answers_dir / filename

    frontmatter = {
        "question": question,
        "sources": source_files,
        "answered_at": today,
        "source_type": "answer",
    }
    fm_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip()

    content = f"---\n{fm_str}\n---\n\n# Q: {question}\n\n{answer}\n"

    filepath.write_text(content, encoding="utf-8")

    if HAS_RICH:
        console.print(f"\n[green]答案已保存到: {filepath.relative_to(wiki_dir.parent)}[/green]")
    else:
        print(f"\n答案已保存到: {filepath.relative_to(wiki_dir.parent)}")

    # 更新 INDEX.md（答案存入后自动纳入搜索索引）
    try:
        index_content = regenerate_index(str(wiki_dir))
        (wiki_dir / "INDEX.md").write_text(index_content, encoding="utf-8")
        if HAS_RICH:
            console.print("[dim]INDEX.md 已更新[/dim]")
    except Exception as e:
        if HAS_RICH:
            console.print(f"[yellow]INDEX.md 更新失败: {e}[/yellow]")


if __name__ == "__main__":
    main()
