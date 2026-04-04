#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编译主引擎：将 raw/ 目录中的 Markdown 文件编译为 wiki/ 条目。

用法：
  python tools/compile_wiki.py              # 增量编译
  python tools/compile_wiki.py --full       # 全量重编译
  python tools/compile_wiki.py --dry-run    # 只显示待处理文件
  python tools/compile_wiki.py --file raw/articles/xxx.md  # 只编译指定文件
"""

import os
import sys
import subprocess
import logging
from datetime import date
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel

# 确保 tools/ 在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.state import StateManager
from tools.llm_client import LLMClient, BudgetExceeded
from tools.parser import parse_wiki_entries
from tools.chunker import chunk_file

console = Console()
logging.basicConfig(level=logging.WARNING)


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_template(templates_dir: str, name: str) -> str:
    path = Path(templates_dir) / name
    return path.read_text(encoding="utf-8")


def read_index(wiki_dir: str) -> str:
    index_path = Path(wiki_dir) / "INDEX.md"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "（索引为空）"


def find_related_entries(query_content: str, wiki_dir: str, top_k: int = 3) -> str:
    """
    简版相关条目搜索（Task 3.1 完成后会被完整版替换）。
    基于关键词重叠，返回最多 top_k 篇相关条目的内容。
    """
    wiki_path = Path(wiki_dir)
    entries = [f for f in wiki_path.glob("*.md") if f.name != "INDEX.md"]

    if not entries:
        return "（暂无已有条目）"

    # 简单关键词匹配评分
    query_words = set(query_content.lower().split())
    scored = []
    for entry in entries:
        content = entry.read_text(encoding="utf-8")
        words = set(content.lower().split())
        score = len(query_words & words)
        scored.append((score, entry))

    scored.sort(reverse=True)
    top = scored[:top_k]

    parts = []
    for score, entry in top:
        if score == 0:
            break
        content = entry.read_text(encoding="utf-8")
        # 只取前 500 字符避免 prompt 过长
        parts.append(f"=== {entry.name} ===\n{content[:500]}")

    return "\n\n".join(parts) if parts else "（暂无相关条目）"


def merge_chunk_entries(
    all_entries: list,
    client: LLMClient,
    merge_template: str,
    language: str,
) -> list:
    """
    对多 chunk 产生的同名条目做 LLM 合并。
    无重复时直接返回；有重复时构造合并 prompt 调 LLM，失败则降级为保留最后一个。
    """
    from collections import defaultdict
    grouped = defaultdict(list)
    for entry in all_entries:
        grouped[entry["filename"]].append(entry)

    final = []
    needs_merge = []

    for fname, group in grouped.items():
        if len(group) == 1:
            final.append(group[0])
        else:
            needs_merge.append((fname, group))

    if not needs_merge:
        return final

    parts = []
    for fname, group in needs_merge:
        for i, entry in enumerate(group):
            parts.append(
                "=== {} (片段 {}/{}) ===\n{}".format(fname, i + 1, len(group), entry["content"])
            )

    prompt = merge_template.format(
        language=language,
        entries_content="\n\n".join(parts),
    )

    response = client.call(prompt)
    merged = parse_wiki_entries(response)
    final.extend(merged)
    return final


def write_wiki_entries(entries: list, wiki_dir: str) -> list:
    """
    将解析后的条目写入 wiki/ 目录。
    返回实际写入的文件路径列表。
    """
    wiki_path = Path(wiki_dir)
    written = []

    for entry in entries:
        filename = entry["filename"]
        content = entry["content"]

        # INDEX.md 单独处理
        if filename == "INDEX.md":
            target = wiki_path / "INDEX.md"
        else:
            target = wiki_path / filename

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))

    return written


def git_commit(message: str):
    """执行 git add -A 和 git commit。"""
    try:
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, text=True
        )
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            logging.warning("git commit 失败: %s", result.stderr)
    except Exception as e:
        logging.warning("git 操作失败: %s", e)


def compile_single_file(
    filepath: str,
    config: dict,
    client: LLMClient,
    state: StateManager,
    template: str,
    wiki_dir: str,
    dry_run: bool = False,
) -> list:
    """
    编译单个 raw 文件，返回生成的 wiki 文件路径列表。
    """
    if dry_run:
        console.print(f"  [cyan]（dry-run）[/cyan] {filepath}")
        return []

    raw_content = Path(filepath).read_text(encoding="utf-8")
    max_kb = config["compile"]["max_file_size_kb"]
    chunks = chunk_file(filepath, max_size_kb=max_kb)

    language = config["wiki"]["language"]
    templates_dir = config["paths"]["templates"]
    today = date.today().isoformat()

    index_content = read_index(wiki_dir)
    related = find_related_entries(raw_content, wiki_dir)

    all_entries = []

    for i, chunk in enumerate(chunks):
        chunk_label = f"chunk {i+1}/{len(chunks)}" if len(chunks) > 1 else "完整"

        prompt = template.format(
            language=language,
            raw_content=chunk,
            index_content=index_content,
            related_entries=related,
            today=today,
        )

        try:
            response = client.call(prompt)
            entries = parse_wiki_entries(response)
            all_entries.extend(entries)
        except BudgetExceeded as e:
            console.print(f"  [red]⚠ 预算超限，停止编译：{e}[/red]")
            raise
        except Exception as e:
            error_msg = str(e)
            state.record_error(filepath, error_msg)
            console.print(f"  [red]✗ 编译失败 ({chunk_label}): {error_msg[:80]}[/red]")
            return []

    # 如果多 chunk，用 LLM 智能合并同名条目（降级时保留最后一个）
    if len(chunks) > 1:
        templates_dir = config["paths"]["templates"]
        merge_tmpl = load_template(templates_dir, "merge.txt")
        language = config["wiki"]["language"]
        try:
            all_entries = merge_chunk_entries(all_entries, client, merge_tmpl, language)
            console.print(
                "  [dim]合并 {} 个 chunk → {} 个条目[/dim]".format(len(chunks), len(all_entries))
            )
        except Exception as e:
            console.print("  [yellow]⚠ 合并失败，降级为简单去重: {}[/yellow]".format(e))
            deduped = {}
            for entry in all_entries:
                deduped[entry["filename"]] = entry
            all_entries = list(deduped.values())

    written = write_wiki_entries(all_entries, wiki_dir)

    # 标记已处理
    file_hash = state.file_hash(filepath)
    state.mark_file_processed(filepath, file_hash, written)

    # 记录费用日志
    summary = client.get_cost_summary()
    state.append_compile_log({
        "file": filepath,
        "outputs": written,
        "cost_usd": summary["cost_usd"],
    })

    return written


@click.command()
@click.option("--full", is_flag=True, help="全量重编译（忽略已处理记录）")
@click.option("--dry-run", is_flag=True, help="只显示待处理文件，不实际编译")
@click.option("--file", "single_file", default=None, help="只编译指定文件")
@click.option("--config", "config_path", default="config.yaml", help="配置文件路径")
def main(full, dry_run, single_file, config_path):
    """LLM 知识库编译引擎 — 将 raw/ 文件编译为 wiki/ 条目。"""
    config = load_config(config_path)
    paths = config["paths"]
    raw_dir = paths["raw"]
    wiki_dir = paths["wiki"]
    state_dir = paths["state"]
    templates_dir = paths["templates"]

    state = StateManager(state_dir)
    template = load_template(templates_dir, "compile.txt")

    # 确定待处理文件列表
    if single_file:
        pending = [single_file] if Path(single_file).exists() else []
    elif full:
        # 全量：扫描所有 raw .md 文件
        pending = [str(f) for f in Path(raw_dir).rglob("*.md")]
    else:
        # 增量：只处理新增/修改的文件
        pending = state.get_unprocessed_files(raw_dir)

    if not pending:
        console.print("[green]✓ 无待处理文件。知识库已是最新。[/green]")
        return

    if dry_run:
        console.print(Panel(
            f"待处理文件（{len(pending)} 个）：\n" +
            "\n".join(f"  • {f}" for f in pending),
            title="[cyan]dry-run 预览[/cyan]"
        ))
        return

    console.print(f"[bold]开始编译[/bold]：{len(pending)} 个文件待处理")

    # 初始化 LLM 客户端
    client = LLMClient(config)

    total = len(pending)
    success = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        BarColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("编译中...", total=total)

        for i, filepath in enumerate(pending):
            filename = Path(filepath).name
            cost_so_far = client.get_cost_summary()["cost_usd"]
            progress.update(
                task,
                description=f"[{i+1}/{total}] {filename} | ${cost_so_far:.3f} 已花费"
            )

            try:
                written = compile_single_file(
                    filepath, config, client, state, template, wiki_dir
                )
                if written:
                    entry_names = [Path(w).name for w in written if Path(w).name != "INDEX.md"]
                    console.print(
                        f"  [green]✓[/green] {filename} → "
                        f"{', '.join(entry_names) or '（无新条目）'}"
                    )
                    # git commit 每个文件
                    git_commit(f"compile: 处理 {filename}")
                    success += 1
                else:
                    failed += 1
            except BudgetExceeded:
                break
            except Exception as e:
                console.print(f"  [red]✗[/red] {filename}: {e}")
                state.record_error(filepath, str(e))
                failed += 1

            progress.advance(task)

    # 最终费用报告
    summary = client.get_cost_summary()
    console.print(Panel(
        f"完成：[green]{success}[/green] 成功 / [red]{failed}[/red] 失败\n"
        f"API 调用：{summary['calls']} 次 | "
        f"Token：{summary['input_tokens']:,} in / {summary['output_tokens']:,} out\n"
        f"费用：[bold]${summary['cost_usd']:.4f}[/bold]",
        title="编译完成"
    ))

    state.set_checkpoint("last_compile", {
        "files_processed": success,
        "files_failed": failed,
        "cost_usd": summary["cost_usd"],
    })


if __name__ == "__main__":
    main()
