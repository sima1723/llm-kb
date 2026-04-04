#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 提取工具：将 PDF 文件转为带 frontmatter 的 Markdown 文件。
用法：
  python tools/pdf_to_md.py <文件或目录>
  python tools/pdf_to_md.py --dry-run raw/papers/
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

try:
    import fitz  # PyMuPDF
except ImportError:
    print("错误：请安装 PyMuPDF：pip install pymupdf")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


def log(msg: str, style: str = ""):
    if HAS_RICH:
        console.print(msg, style=style)
    else:
        print(msg)


def extract_pdf(pdf_path: Path, output_dir: Path = None, dry_run: bool = False) -> Path | None:
    """
    提取单个 PDF 文件为 Markdown。
    返回输出文件路径，或 None（跳过/失败）。
    """
    if output_dir is None:
        output_dir = pdf_path.parent

    md_path = output_dir / (pdf_path.stem + ".md")

    # 幂等：.md 存在且比 PDF 新则跳过
    if md_path.exists():
        pdf_mtime = pdf_path.stat().st_mtime
        md_mtime = md_path.stat().st_mtime
        if md_mtime > pdf_mtime:
            log(f"  跳过（已是最新）：{pdf_path.name}", "dim")
            return None

    if dry_run:
        log(f"  [dry-run] 将处理：{pdf_path}", "yellow")
        return md_path

    try:
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)

        # 收集所有文本块及字体大小信息
        blocks_data = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") != 0:  # 只要文本块
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        size = span.get("size", 0)
                        if text:
                            blocks_data.append({"text": text, "size": size})

        if not blocks_data:
            log(f"  警告：PDF 无可提取文本（可能是扫描件）：{pdf_path.name}", "yellow")
            doc.close()
            return None

        # 推断标题层级：按字体大小排序
        sizes = sorted(set(b["size"] for b in blocks_data), reverse=True)
        size_to_level = {}
        for i, s in enumerate(sizes[:3]):  # 最多3级标题
            size_to_level[s] = i + 1

        # 构建 Markdown 内容
        lines = []
        prev_text = ""
        for b in blocks_data:
            text = b["text"]
            size = b["size"]

            if text == prev_text:  # 去重
                continue
            prev_text = text

            level = size_to_level.get(size, 0)
            if level == 1:
                lines.append(f"\n# {text}\n")
            elif level == 2:
                lines.append(f"\n## {text}\n")
            elif level == 3:
                lines.append(f"\n### {text}\n")
            else:
                lines.append(text + " ")

        doc.close()

        # 清理多余空行
        content = "\n".join(lines)
        import re
        content = re.sub(r'\n{4,}', '\n\n\n', content)

        # 构建 frontmatter
        frontmatter = (
            "---\n"
            f"source_type: paper\n"
            f"source_file: {pdf_path.name}\n"
            f"extracted_at: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"page_count: {page_count}\n"
            "---\n\n"
        )

        md_path.write_text(frontmatter + content, encoding="utf-8")
        log(f"  ✓ {pdf_path.name} → {md_path.name} ({page_count} 页)", "green")
        return md_path

    except Exception as e:
        log(f"  ✗ 处理失败 {pdf_path.name}：{e}", "red")
        return None


def process_path(path: Path, dry_run: bool = False):
    """处理单个文件或目录下的所有 PDF。"""
    if path.is_file():
        pdfs = [path] if path.suffix.lower() == ".pdf" else []
    elif path.is_dir():
        pdfs = list(path.rglob("*.pdf")) + list(path.rglob("*.PDF"))
    else:
        log(f"错误：路径不存在：{path}", "red")
        return

    if not pdfs:
        log(f"未找到 PDF 文件：{path}", "yellow")
        return

    log(f"\n找到 {len(pdfs)} 个 PDF 文件", "bold")

    if HAS_RICH and not dry_run:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("提取中...", total=len(pdfs))
            for pdf in pdfs:
                progress.update(task, description=f"处理：{pdf.name[:40]}")
                extract_pdf(pdf, dry_run=dry_run)
                progress.advance(task)
    else:
        for pdf in pdfs:
            extract_pdf(pdf, dry_run=dry_run)

    log("\n完成。", "bold green")


def main():
    parser = argparse.ArgumentParser(
        description="将 PDF 文件提取为 Markdown（存入同目录）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n  python tools/pdf_to_md.py raw/papers/\n  python tools/pdf_to_md.py --dry-run raw/papers/",
    )
    parser.add_argument("path", nargs="?", default="raw/papers", help="PDF 文件或目录路径（默认：raw/papers）")
    parser.add_argument("--dry-run", action="store_true", help="只列出将处理的文件，不实际执行")
    args = parser.parse_args()

    if args.dry_run:
        log("[dry-run 模式] 不会实际写入文件\n", "yellow")

    process_path(Path(args.path), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
