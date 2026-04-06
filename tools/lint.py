#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库健康检查工具 — 检测断链、孤立条目、格式问题等。

CLI:
  python tools/lint.py                # 只报告
  python tools/lint.py --fix          # 自动修复本地可修复的问题
  python tools/lint.py --ai-fix       # 调用 LLM 修复复杂问题（Task 4.2）
  python tools/lint.py --dry-run      # 列出将修复什么但不执行
"""

import os
import re
import sys
import subprocess
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import click
import yaml

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

console = Console() if HAS_RICH else None

WIKI_DIR = _HERE / "wiki"
CONFIG_FILE = _HERE / "config.yaml"

# ─── 数据结构 ───────────────────────────────────────────────────────────────

class Issue:
    """一个检测到的问题"""
    TYPES = {
        "broken_link":  "断链",
        "orphan":       "孤立条目",
        "missing_fm":   "缺失frontmatter",
        "index_stale":  "INDEX不同步",
        "empty_entry":  "空条目",
        "duplicate":    "疑似重复",
    }
    SEVERITY = {
        "broken_link":  "warning",
        "orphan":       "info",
        "missing_fm":   "warning",
        "index_stale":  "info",
        "empty_entry":  "warning",
        "duplicate":    "info",
    }

    def __init__(self, issue_type: str, filepath: str, detail: str,
                 auto_fixable: bool = False, ai_fixable: bool = False):
        self.issue_type = issue_type
        self.filepath = filepath
        self.detail = detail
        self.auto_fixable = auto_fixable
        self.ai_fixable = ai_fixable
        self.status = "发现"  # 发现 / 已修复 / 需人工

    @property
    def type_name(self) -> str:
        return self.TYPES.get(self.issue_type, self.issue_type)

    @property
    def severity(self) -> str:
        return self.SEVERITY.get(self.issue_type, "info")


# ─── 检测逻辑 ───────────────────────────────────────────────────────────────

def load_all_entries(wiki_dir: Path) -> list[dict]:
    """加载所有 wiki 条目（包括 answers/slides/ 子目录）"""
    entries = []
    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        raw = md_file.read_text(encoding="utf-8", errors="ignore")
        # 解析 frontmatter
        fm = {}
        pattern = re.compile(r'^---\n(.*?)\n---\n', re.DOTALL)
        m = pattern.match(raw)
        if m:
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except Exception:
                fm = {}
            body = raw[m.end():]
        else:
            body = raw

        links = re.findall(r'\[\[(.+?)\]\]', raw)
        entries.append({
            "filepath": md_file,
            "rel": md_file.relative_to(wiki_dir),
            "filename": str(md_file.relative_to(wiki_dir)),
            "stem": md_file.stem,
            "frontmatter": fm,
            "body": body,
            "raw": raw,
            "links": links,
        })
    return entries


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def check_broken_links(entries: list[dict], wiki_dir: Path) -> list[Issue]:
    """断链：[[xxx]] 指向不存在的 wiki/xxx.md"""
    issues = []
    existing_stems = {e["stem"] for e in entries}
    for entry in entries:
        for lk in entry["links"]:
            if lk not in existing_stems:
                issues.append(Issue(
                    "broken_link",
                    entry["filename"],
                    f"[[{lk}]] 指向不存在的条目",
                    auto_fixable=True,
                ))
    return issues


def check_orphans(entries: list[dict]) -> list[Issue]:
    """孤立条目：没有任何其他条目链接到它"""
    issues = []
    all_links: set[str] = set()
    for entry in entries:
        all_links.update(entry["links"])
    for entry in entries:
        # answers/ 和 slides/ 下的不算孤立
        if "answers" in str(entry["rel"]) or "slides" in str(entry["rel"]):
            continue
        if entry["stem"] not in all_links:
            issues.append(Issue(
                "orphan",
                entry["filename"],
                "没有任何条目链接到此条目",
                auto_fixable=False,
                ai_fixable=False,
            ))
    return issues


def check_missing_frontmatter(entries: list[dict]) -> list[Issue]:
    """缺失 frontmatter 或必要字段不完整"""
    required_fields = {"sources", "last_updated"}
    issues = []
    for entry in entries:
        # answers 和 slides 用不同字段
        if "answers" in str(entry["rel"]) or "slides" in str(entry["rel"]):
            continue
        if not entry["frontmatter"]:
            issues.append(Issue(
                "missing_fm",
                entry["filename"],
                "缺失 frontmatter",
                auto_fixable=True,
            ))
        else:
            missing = required_fields - set(entry["frontmatter"].keys())
            if missing:
                issues.append(Issue(
                    "missing_fm",
                    entry["filename"],
                    f"frontmatter 缺失字段: {', '.join(sorted(missing))}",
                    auto_fixable=True,
                ))
    return issues


def check_index_stale(entries: list[dict], wiki_dir: Path) -> list[Issue]:
    """INDEX.md 与实际文件不同步"""
    issues = []
    index_path = wiki_dir / "INDEX.md"
    if not index_path.exists():
        issues.append(Issue("index_stale", "INDEX.md", "INDEX.md 不存在", auto_fixable=True))
        return issues

    index_content = index_path.read_text(encoding="utf-8", errors="ignore")
    # 简单检查：index 中列出的条目数 vs 实际条目数
    main_entries = [e for e in entries
                    if "answers" not in str(e["rel"]) and "slides" not in str(e["rel"])]
    # 扫描 INDEX 里的 [[链接]] 数量
    index_links = set(re.findall(r'\[\[(.+?)\]\]', index_content))
    main_stems = {e["stem"] for e in main_entries}
    unlisted = main_stems - index_links
    if unlisted:
        issues.append(Issue(
            "index_stale",
            "INDEX.md",
            f"{len(unlisted)} 个条目未列入 INDEX: {', '.join(sorted(unlisted)[:5])}{'...' if len(unlisted) > 5 else ''}",
            auto_fixable=True,
        ))
    return issues


def check_empty_entries(entries: list[dict], min_length: int = 100) -> list[Issue]:
    """空条目：正文字数 < min_entry_length"""
    issues = []
    for entry in entries:
        body_len = len(entry["body"].replace(' ', '').replace('\n', ''))
        if body_len < min_length:
            issues.append(Issue(
                "empty_entry",
                entry["filename"],
                f"条目正文仅 {body_len} 字（最低 {min_length} 字）",
                auto_fixable=False,
                ai_fixable=True,
            ))
    return issues


def check_duplicates(entries: list[dict], threshold: float = 0.80) -> list[Issue]:
    """重复条目：文件名相似度 > threshold。用首字符前缀分组减少比较量。"""
    from collections import defaultdict
    issues = []
    main_entries = [e for e in entries
                    if "answers" not in str(e["rel"]) and "slides" not in str(e["rel"])]

    # 按首字符分组（相似文件名通常首字符相同），避免 O(n²) 全量比较
    groups: dict[str, list] = defaultdict(list)
    for e in main_entries:
        groups[e["stem"][0].lower() if e["stem"] else ""].append(e)

    seen_pairs: set[tuple] = set()
    for group in groups.values():
        for i, e1 in enumerate(group):
            for e2 in group[i + 1:]:
                pair = tuple(sorted([e1["stem"], e2["stem"]]))
                if pair in seen_pairs:
                    continue
                ratio = SequenceMatcher(None, e1["stem"], e2["stem"]).ratio()
                if ratio >= threshold:
                    seen_pairs.add(pair)
                    issues.append(Issue(
                        "duplicate",
                        e1["filename"],
                        f"与 {e2['filename']} 文件名相似度 {ratio:.0%}",
                        auto_fixable=False,
                        ai_fixable=True,
                    ))
    return issues


def run_all_checks(wiki_dir: Path, config: dict) -> list[Issue]:
    """运行所有检查，返回问题列表"""
    entries = load_all_entries(wiki_dir)
    min_len = config.get("wiki", {}).get("min_entry_length", 100)

    all_issues: list[Issue] = []
    all_issues.extend(check_broken_links(entries, wiki_dir))
    all_issues.extend(check_orphans(entries))
    all_issues.extend(check_missing_frontmatter(entries))
    all_issues.extend(check_index_stale(entries, wiki_dir))
    all_issues.extend(check_empty_entries(entries, min_len))
    all_issues.extend(check_duplicates(entries))
    return all_issues


# ─── 自动修复 ────────────────────────────────────────────────────────────────

def fix_broken_link(issue: Issue, wiki_dir: Path, dry_run: bool) -> bool:
    """断链修复：创建 stub 条目"""
    m = re.search(r'\[\[(.+?)\]\]', issue.detail)
    if not m:
        return False
    concept = m.group(1)
    stub_path = wiki_dir / f"{concept}.md"
    if stub_path.exists():
        return False
    if dry_run:
        print(f"  [dry-run] 将创建 stub: wiki/{concept}.md")
        return True
    today = datetime.now().strftime("%Y-%m-%d")
    stub_content = (
        f"---\nrelated_concepts: []\nsources: []\nlast_updated: {today}\ntags: [stub]\n---\n\n"
        f"# {concept}\n\n> ⚠️ 此条目为自动生成的 stub，尚待编译填充。\n\n"
        f"## 定义\n待补充。\n"
    )
    stub_path.write_text(stub_content, encoding="utf-8")
    issue.status = "已修复"
    return True


def fix_missing_frontmatter(issue: Issue, wiki_dir: Path, dry_run: bool) -> bool:
    """补充缺失的 frontmatter 字段"""
    fp = (wiki_dir / issue.filepath).resolve()
    # 防止路径穿越：确保目标文件仍在 wiki_dir 内
    if not str(fp).startswith(str(wiki_dir.resolve())):
        return False
    if not fp.exists():
        return False
    raw = fp.read_text(encoding="utf-8", errors="ignore")
    today = datetime.now().strftime("%Y-%m-%d")

    pattern = re.compile(r'^---\n(.*?)\n---\n', re.DOTALL)
    m = pattern.match(raw)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            fm = {}
        body = raw[m.end():]
    else:
        fm = {}
        body = raw

    changed = False
    if "sources" not in fm:
        fm["sources"] = []
        changed = True
    if "last_updated" not in fm:
        fm["last_updated"] = today
        changed = True

    if not changed:
        return False

    if dry_run:
        print(f"  [dry-run] 将补充 frontmatter 字段到 {issue.filepath}")
        return True

    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
    new_content = f"---\n{fm_str}\n---\n{body}"
    fp.write_text(new_content, encoding="utf-8")
    issue.status = "已修复"
    return True


def fix_index_stale(wiki_dir: Path, dry_run: bool) -> bool:
    """重新生成 INDEX.md"""
    if dry_run:
        print("  [dry-run] 将重新生成 INDEX.md")
        return True
    try:
        from tools.indexer import regenerate_index
        content = regenerate_index(str(wiki_dir))
        (wiki_dir / "INDEX.md").write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"  重新生成 INDEX.md 失败: {e}")
        return False


def apply_local_fixes(issues: list[Issue], wiki_dir: Path, dry_run: bool):
    """应用所有本地可修复的问题"""
    index_fixed = False
    for issue in issues:
        if issue.issue_type == "broken_link" and issue.auto_fixable:
            fix_broken_link(issue, wiki_dir, dry_run)
        elif issue.issue_type == "missing_fm" and issue.auto_fixable:
            fix_missing_frontmatter(issue, wiki_dir, dry_run)
        elif issue.issue_type == "index_stale" and not index_fixed:
            index_fixed = fix_index_stale(wiki_dir, dry_run)
            if index_fixed:
                for iss in issues:
                    if iss.issue_type == "index_stale":
                        iss.status = "已修复"


# ─── AI 修复（Task 4.2）────────────────────────────────────────────────────

def apply_ai_fixes(issues: list[Issue], wiki_dir: Path, config: dict, dry_run: bool):
    """
    对 ai_fixable 的问题，调用 LLM 修复。
    只处理未被本地修复的问题。
    """
    ai_issues = [iss for iss in issues if iss.ai_fixable and iss.status == "发现"]
    if not ai_issues:
        print("没有需要 AI 修复的问题。")
        return

    # 加载模板
    template_path = _HERE / "templates" / "lint_ai.txt"
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
    else:
        template = (
            "你是知识库维护专家。语言：{language}\n"
            "问题：\n<issues>\n{issues}\n</issues>\n"
            "相关条目：\n<entries>\n{entries}\n</entries>\n"
            "请修复并输出：\n<wiki_entry><filename>...</filename><action>update</action><content>...</content></wiki_entry>"
        )

    language = config.get("wiki", {}).get("language", "zh")
    lint_max_tokens = config.get("llm", {}).get("max_tokens_by_tool", {}).get("lint_ai")

    # 按文件分组
    file_issues: dict[str, list[Issue]] = {}
    for iss in ai_issues:
        file_issues.setdefault(iss.filepath, []).append(iss)

    try:
        from tools.llm_client import LLMClient
        from tools.parser import parse_wiki_entries
        client = LLMClient(config, tool="lint_ai")
    except Exception as e:
        print(f"初始化 LLM 失败: {e}")
        return

    if dry_run:
        for filepath in file_issues:
            print(f"  [dry-run] 将调用 AI 修复: {filepath}")
        return

    # 将所有文件的问题合并到一次 LLM 调用，减少 API 请求次数
    all_issues_desc_parts = []
    all_entries_parts = []
    valid_file_issues: dict[str, list[Issue]] = {}

    MAX_ENTRY_CHARS = 3000  # 每个条目截断上限
    for filepath, file_issue_list in file_issues.items():
        abs_path = wiki_dir / filepath
        if not abs_path.exists():
            continue
        entry_content = abs_path.read_text(encoding="utf-8", errors="ignore")[:MAX_ENTRY_CHARS]
        issues_desc = "\n".join(f"- [{iss.type_name}] {iss.detail}" for iss in file_issue_list)
        all_issues_desc_parts.append(f"[{filepath}]\n{issues_desc}")
        all_entries_parts.append(f"=== {filepath} ===\n{entry_content}")
        valid_file_issues[filepath] = file_issue_list

    if not valid_file_issues:
        return

    batch_issues = "\n\n".join(all_issues_desc_parts)
    batch_entries = "\n\n".join(all_entries_parts)
    prompt = template.format(language=language, issues=batch_issues, entries=batch_entries)

    try:
        response = client.call(prompt, max_tokens=lint_max_tokens)
        entries = parse_wiki_entries(response)
        for entry in entries:
            out_path = wiki_dir / entry["filename"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(entry["content"], encoding="utf-8")
            # 标记对应文件的所有问题为已修复
            for fp_issues in valid_file_issues.values():
                for iss in fp_issues:
                    if iss.filepath == entry["filename"] or entry["filename"].endswith(iss.filepath):
                        iss.status = "已修复"
            if HAS_RICH:
                console.print(f"  [green]AI 修复: {entry['filename']}[/green]")
            else:
                print(f"  AI 修复: {entry['filename']}")
    except Exception as e:
        if HAS_RICH:
            console.print(f"  [red]AI 修复失败: {e}[/red]")
        else:
            print(f"  AI 修复失败: {e}")

    summary = client.get_cost_summary()
    if HAS_RICH:
        console.print(f"[dim]AI 修复费用: ${summary['cost_usd']:.4f}[/dim]")
    else:
        print(f"AI 修复费用: ${summary['cost_usd']:.4f}")


# ─── 输出报告 ─────────────────────────────────────────────────────────────────

def print_report(issues: list[Issue]):
    """用 rich 表格或纯文本输出检测报告"""
    if not issues:
        if HAS_RICH:
            console.print("[green]✓ 知识库健康，未发现问题[/green]")
        else:
            print("✓ 知识库健康，未发现问题")
        return

    if HAS_RICH:
        table = Table(title=f"Lint 报告（共 {len(issues)} 个问题）", box=box.SIMPLE_HEAVY)
        table.add_column("类型", style="yellow", width=12)
        table.add_column("文件", style="cyan", max_width=35)
        table.add_column("详情", max_width=50)
        table.add_column("状态", width=8)
        table.add_column("可修复", width=10)

        for iss in issues:
            sev_color = "red" if iss.severity == "error" else "yellow" if iss.severity == "warning" else "dim"
            fix_hint = "[green]--fix[/green]" if iss.auto_fixable else ("[blue]--ai-fix[/blue]" if iss.ai_fixable else "[dim]人工[/dim]")
            status_color = "green" if iss.status == "已修复" else "yellow"
            table.add_row(
                f"[{sev_color}]{iss.type_name}[/{sev_color}]",
                iss.filepath,
                iss.detail,
                f"[{status_color}]{iss.status}[/{status_color}]",
                fix_hint,
            )
        console.print(table)
    else:
        print(f"\nLint 报告（共 {len(issues)} 个问题）")
        print("-" * 80)
        for iss in issues:
            fix = "--fix" if iss.auto_fixable else ("--ai-fix" if iss.ai_fixable else "人工")
            print(f"[{iss.type_name}] {iss.filepath}")
            print(f"  {iss.detail}  状态:{iss.status}  修复:{fix}")
        print("-" * 80)


# ─── CLI ───────────────────────────────────────────────────────────────────

@click.command()
@click.option("--fix", "do_fix", is_flag=True, help="自动修复本地可修复的问题")
@click.option("--ai-fix", "do_ai_fix", is_flag=True, help="调用 LLM 修复复杂问题")
@click.option("--dry-run", is_flag=True, help="列出将修复什么但不执行")
@click.option("--wiki-dir", default=None, help="wiki 目录路径")
def main(do_fix: bool, do_ai_fix: bool, dry_run: bool, wiki_dir: Optional[str]):
    """知识库健康检查"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR
    config = _load_config()

    if HAS_RICH:
        with console.status("[cyan]正在扫描知识库...[/cyan]"):
            issues = run_all_checks(wd, config)
    else:
        print("正在扫描知识库...")
        issues = run_all_checks(wd, config)

    if do_fix or dry_run:
        apply_local_fixes(issues, wd, dry_run)

    if do_ai_fix:
        apply_ai_fixes(issues, wd, config, dry_run)

    print_report(issues)

    # 统计
    fixed = sum(1 for i in issues if i.status == "已修复")
    unfixed = len(issues) - fixed
    if HAS_RICH:
        console.print(f"\n[dim]总计: {len(issues)} 问题  |  已修复: {fixed}  |  待处理: {unfixed}[/dim]")
    else:
        print(f"\n总计: {len(issues)} 问题  |  已修复: {fixed}  |  待处理: {unfixed}")

    # git commit（如有修复）
    if fixed > 0 and not dry_run:
        try:
            subprocess.run(
                ["git", "-C", str(_HERE), "add", "-A"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(_HERE), "commit",
                 "-m", f"fix: lint 自动修复 {fixed} 个问题"],
                check=True, capture_output=True,
            )
            if HAS_RICH:
                console.print(f"[green]git commit: lint 修复 {fixed} 个问题[/green]")
        except subprocess.CalledProcessError:
            pass  # 没有变更时正常


if __name__ == "__main__":
    main()
