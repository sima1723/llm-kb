#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stub 填充工具 — 用 LLM 训练知识为"待补充"stub 条目生成初稿内容。

CLI:
  python tools/stub_fill.py                   # 填充所有 stub 条目
  python tools/stub_fill.py --entry 规模定律   # 只填充指定条目
  python tools/stub_fill.py --dry-run          # 预览待填充列表，不调用 API
"""

import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import click
import yaml

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from tools.llm_client import LLMClient, BudgetExceeded
from tools.parser import parse_wiki_entries
from tools.indexer import regenerate_index

console = Console() if HAS_RICH else None

WIKI_DIR = _HERE / "wiki"
CONFIG_FILE = _HERE / "config.yaml"

# ─── Prompt ────────────────────────────────────────────────────────────────

_FILL_PROMPT = """\
你是一位知识库编撰者。请根据你的训练知识为以下 wiki 条目生成完整内容。语言：{language}

## 目标条目
概念名称：{concept_name}

## 知识库中的关联条目（供参考，建立双向链接）
<related_entries>
{related_entries}
</related_entries>

## 要求
1. 定义简洁准确（3-5句）
2. 关键要点列出 4-6 条
3. 详细说明 200-400 字，深入讲解核心机制、原理或应用
4. 关联概念中必须引用知识库中已有的相关条目（用 [[条目名]] 格式）
5. 内容必须准确，不要捏造参考文献；来源节留空即可

## 输出格式

<wiki_entry>
<filename>{concept_name}.md</filename>
<action>update</action>
<content>
---
related_concepts: [概念A, 概念B]
sources: [llm-knowledge]
last_updated: {today}
---

## 定义
（定义内容）

## 关键要点
- 要点1
- 要点2

## 详细说明
（详细内容）

## 关联概念
- [[概念A]] — 关系说明

## 来源
- 基于 LLM 训练知识生成（待补充原始资料）
</content>
</wiki_entry>
"""


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def _is_stub(filepath: Path) -> bool:
    """判断一个 wiki 条目是否是未填充的 stub。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return False
    # 两种 stub 标志：frontmatter 中有 tags: [stub]，或正文有"待补充"
    has_stub_tag = bool(re.search(r'^tags:.*\bstub\b', content, re.MULTILINE))
    has_placeholder = "待补充" in content
    return has_stub_tag or has_placeholder


def _find_stubs() -> list[Path]:
    """返回所有 stub 条目路径（排除 INDEX.md 和 answers/）。"""
    stubs = []
    for f in WIKI_DIR.glob("*.md"):
        if f.name == "INDEX.md":
            continue
        if _is_stub(f):
            stubs.append(f)
    return sorted(stubs)


def _collect_related_context(concept_name: str, max_entries: int = 5) -> str:
    """从 wiki 中收集与目标概念相关的已填充条目内容（最多 max_entries 篇）。"""
    entries = []
    for f in WIKI_DIR.glob("*.md"):
        if f.name == "INDEX.md" or f.name == f"{concept_name}.md":
            continue
        if _is_stub(f):
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        # 简单关键词匹配：条目名出现在内容中，或内容标题与概念相关
        name_lower = concept_name.lower()
        if name_lower in content.lower() or concept_name in content:
            entries.append((f.stem, content))

    # 最多取 max_entries 篇，并截断过长内容
    result_parts = []
    for stem, content in entries[:max_entries]:
        truncated = content[:800] + "..." if len(content) > 800 else content
        result_parts.append(f"### [[{stem}]]\n{truncated}")

    if not result_parts:
        # 返回最多 3 篇已填充条目作为通用上下文
        filled = [f for f in WIKI_DIR.glob("*.md")
                  if f.name != "INDEX.md" and not _is_stub(f)][:3]
        for f in filled:
            content = f.read_text(encoding="utf-8", errors="ignore")
            truncated = content[:600] + "..." if len(content) > 600 else content
            result_parts.append(f"### [[{f.stem}]]\n{truncated}")

    return "\n\n".join(result_parts) if result_parts else "（暂无相关条目）"


def _write_entry(filepath: Path, content: str) -> None:
    filepath.write_text(content, encoding="utf-8")


# ─── 核心填充逻辑 ─────────────────────────────────────────────────────────────

def fill_stub(stub_path: Path, client: LLMClient, config: dict) -> bool:
    """
    为单个 stub 条目调用 LLM 生成内容，写回文件。
    返回 True 表示成功，False 表示失败。
    """
    concept_name = stub_path.stem
    language = config.get("wiki", {}).get("language", "zh")
    related = _collect_related_context(concept_name)

    prompt = _FILL_PROMPT.format(
        language=language,
        concept_name=concept_name,
        related_entries=related,
        today=str(date.today()),
    )

    try:
        response = client.call(prompt)
    except BudgetExceeded as e:
        if console:
            console.print(f"[red]预算超出，停止填充：{e}[/red]")
        else:
            print(f"预算超出，停止填充：{e}")
        return False
    except Exception as e:
        if console:
            console.print(f"[yellow]  ⚠ {concept_name} 调用失败：{e}[/yellow]")
        else:
            print(f"  警告：{concept_name} 调用失败：{e}")
        return False

    entries = parse_wiki_entries(response)
    if not entries:
        if console:
            console.print(f"[yellow]  ⚠ {concept_name} 响应解析失败[/yellow]")
        else:
            print(f"  警告：{concept_name} 响应解析失败")
        return False

    # 取第一个 entry（通常只有一个）
    entry = entries[0]
    _write_entry(stub_path, entry["content"])
    return True


# ─── CLI ────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--entry", default=None, help="只填充指定条目名（不含 .md）")
@click.option("--dry-run", is_flag=True, help="只列出待填充条目，不调用 API")
def main(entry: Optional[str], dry_run: bool):
    """用 LLM 训练知识填充 wiki 中的 stub（待补充）条目。"""
    config = _load_config()

    # 确定目标列表
    if entry:
        target_path = WIKI_DIR / f"{entry}.md"
        if not target_path.exists():
            click.echo(f"错误：条目 '{entry}' 不存在于 wiki/")
            sys.exit(1)
        if not _is_stub(target_path):
            click.echo(f"条目 '{entry}' 已有内容，无需填充。")
            sys.exit(0)
        stubs = [target_path]
    else:
        stubs = _find_stubs()

    if not stubs:
        if console:
            console.print("[green]✓ 没有待填充的 stub 条目[/green]")
        else:
            print("没有待填充的 stub 条目")
        return

    # dry-run：只列出
    if dry_run:
        if console:
            t = Table(title=f"待填充 stub 条目（共 {len(stubs)} 个）", box=box.SIMPLE)
            t.add_column("条目名", style="cyan")
            for s in stubs:
                t.add_row(s.stem)
            console.print(t)
        else:
            print(f"待填充 stub 条目（共 {len(stubs)} 个）：")
            for s in stubs:
                print(f"  - {s.stem}")
        return

    # 实际填充
    client = LLMClient(config)
    success, failed = 0, []

    if console:
        console.print(Panel(f"开始填充 {len(stubs)} 个 stub 条目", style="bold blue"))
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("填充中...", total=len(stubs))
            for stub in stubs:
                progress.update(task, description=f"填充 {stub.stem}")
                ok = fill_stub(stub, client, config)
                if ok:
                    success += 1
                    console.print(f"  [green]✓[/green] {stub.stem}")
                else:
                    failed.append(stub.stem)
                    console.print(f"  [red]✗[/red] {stub.stem}")
                progress.advance(task)
    else:
        for stub in stubs:
            print(f"填充：{stub.stem} ...")
            ok = fill_stub(stub, client, config)
            if ok:
                success += 1
                print(f"  ✓ 完成")
            else:
                failed.append(stub.stem)
                print(f"  ✗ 失败")

    # 重建索引
    try:
        regenerate_index(str(WIKI_DIR))
    except Exception:
        pass

    # 汇报
    summary = f"\n填充完成：{success} 成功"
    if failed:
        summary += f"，{len(failed)} 失败：{', '.join(failed)}"
    cost = getattr(client, 'total_cost', None)
    if cost:
        summary += f"  |  本次花费约 ${cost:.4f}"

    if console:
        console.print(Panel(summary, style="bold green" if not failed else "bold yellow"))
    else:
        print(summary)


if __name__ == "__main__":
    main()
