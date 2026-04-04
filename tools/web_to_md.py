#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网页抓取工具：将网页抓取并转为带 frontmatter 的 Markdown 文件。
用法：
  python tools/web_to_md.py <URL>
  python tools/web_to_md.py --help
"""

import sys
import re
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from html.parser import HTMLParser


# ── HTML 解析器 ──────────────────────────────────────────────────

class ArticleParser(HTMLParser):
    """从 HTML 提取标题和正文，忽略 nav/footer/script 等噪音标签。"""

    SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside",
                 "noscript", "iframe", "form", "button", "select", "input"}
    BLOCK_TAGS = {"p", "div", "article", "section", "main",
                  "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "blockquote", "pre", "code", "td", "th"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.title = ""
        self.lines = []
        self._skip_depth = 0
        self._current_tag = ""
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if self._skip_depth > 0:
            self._skip_depth += 1
            return
        if tag in self.SKIP_TAGS:
            self._skip_depth = 1
            return
        self._current_tag = tag
        if tag in self.BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag):
        if self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS:
            self._flush()
            self._current_tag = ""

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self._buf.append(text)

    def _flush(self):
        text = " ".join(self._buf).strip()
        self._buf = []
        if not text:
            return
        tag = self._current_tag
        if tag in self.HEADING_TAGS:
            level = int(tag[1])
            prefix = "#" * level
            # 抓取第一个 h1 作为标题
            if tag == "h1" and not self.title:
                self.title = text
            self.lines.append(f"\n{prefix} {text}\n")
        else:
            self.lines.append(text)

    def get_markdown(self) -> str:
        self._flush()
        raw = "\n".join(self.lines)
        # 合并多余空行
        raw = re.sub(r'\n{4,}', '\n\n\n', raw)
        return raw.strip()


# ── 工具函数 ─────────────────────────────────────────────────────

def slugify(text: str, max_len: int = 50) -> str:
    """将标题转为 ASCII slug，用于文件名。"""
    # 尝试 ASCII 化
    try:
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    except Exception:
        ascii_text = text

    if not ascii_text.strip():
        # 全中文标题，保留原文（限长）
        ascii_text = text

    slug = re.sub(r'[^\w\s-]', '', ascii_text).strip().lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug[:max_len].strip("-") or "untitled"


def already_clipped(url: str, raw_dir: Path) -> bool:
    """检查 URL 是否已被抓取（扫描 frontmatter）。"""
    for md_file in raw_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if f"source_url: {url}" in content:
                return True
        except Exception:
            pass
    return False


def fetch_page(url: str) -> tuple[str, str]:
    """
    抓取网页，返回 (html, final_url)。
    抛出异常时由调用方处理。
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; llm-kb/1.0; "
            "+https://github.com/llm-kb)"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=15) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        html = resp.read().decode(charset, errors="replace")
        final_url = resp.url
    return html, final_url


def html_to_md(html: str) -> tuple[str, str]:
    """解析 HTML，返回 (title, markdown_content)。"""
    # 先尝试从 <title> 标签提取标题
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    html_title = title_match.group(1).strip() if title_match else ""

    parser = ArticleParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    title = parser.title or html_title or "untitled"
    # 清理 HTML 实体
    title = re.sub(r'&[a-z]+;', ' ', title).strip()

    content = parser.get_markdown()
    return title, content


# ── 主逻辑 ───────────────────────────────────────────────────────

def clip_url(url: str, output_dir: Path, dry_run: bool = False) -> Path | None:
    """抓取 URL 并保存为 Markdown，返回输出路径或 None。"""
    try:
        from rich.console import Console
        console = Console()
        def log(msg, style=""):
            console.print(msg, style=style)
    except ImportError:
        def log(msg, style=""):
            print(msg)

    # 检查是否已抓取
    raw_root = output_dir.parent.parent if output_dir.name == "articles" else output_dir.parent
    articles_dir = raw_root / "raw" / "articles" if (raw_root / "raw").exists() else output_dir

    if already_clipped(url, output_dir):
        log(f"已抓取过，跳过：{url}", "yellow")
        return None

    if dry_run:
        log(f"[dry-run] 将抓取：{url}", "yellow")
        return None

    log(f"正在抓取：{url}")
    try:
        html, final_url = fetch_page(url)
    except HTTPError as e:
        log(f"✗ HTTP 错误 {e.code}：{url}", "red")
        return None
    except URLError as e:
        log(f"✗ 网络错误：{e.reason}", "red")
        return None
    except Exception as e:
        log(f"✗ 抓取失败：{e}", "red")
        return None

    title, content = html_to_md(html)

    today = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(title)
    filename = f"{today}-{slug}.md"
    output_path = output_dir / filename

    frontmatter = (
        "---\n"
        f"source_type: article\n"
        f"source_url: {final_url}\n"
        f"clipped_at: {today}\n"
        f"title: \"{title}\"\n"
        "---\n\n"
    )

    # 加页面标题作为一级标题（如果内容中没有）
    if not content.startswith("# "):
        content = f"# {title}\n\n{content}"

    output_path.write_text(frontmatter + content, encoding="utf-8")
    log(f"✓ 已保存：{output_path}", "green")
    log(f"  标题：{title}")
    log(f"  字符数：{len(content)}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="将网页抓取并转为 Markdown，保存到 raw/articles/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='示例：\n  python tools/web_to_md.py "https://example.com"\n  python tools/web_to_md.py --output raw/articles/ "https://example.com"',
    )
    parser.add_argument("url", help="要抓取的网页 URL")
    parser.add_argument("--output", default="raw/articles", help="输出目录（默认：raw/articles）")
    parser.add_argument("--dry-run", action="store_true", help="只显示将要执行的操作，不实际抓取")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    clip_url(args.url, output_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
