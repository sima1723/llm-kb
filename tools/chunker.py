#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件分段器：将大文件按标题或段落切分为多个 chunk。
"""

import re
from pathlib import Path
from typing import Optional


def _extract_frontmatter(content: str) -> tuple:
    """
    提取 YAML frontmatter。
    返回 (frontmatter_str, body_str)，frontmatter 可为空字符串。
    """
    if content.startswith('---'):
        end = content.find('\n---', 3)
        if end != -1:
            fm = content[:end + 4]  # 包含结尾 ---
            body = content[end + 4:].lstrip('\n')
            return fm, body
    return '', content


def _split_by_headings(body: str) -> list:
    """按 ## 二级标题分段，保留标题本身。"""
    # 按 ## 标题分割（保留分隔符）
    parts = re.split(r'(?=^## )', body, flags=re.MULTILINE)
    return [p for p in parts if p.strip()]


def _split_by_paragraphs(text: str, max_bytes: int) -> list:
    """按段落（双换行）进一步分割，直到每段小于 max_bytes。"""
    paragraphs = re.split(r'\n\n+', text)
    chunks = []
    current = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para.encode('utf-8'))
        if current_size + para_size > max_bytes and current:
            chunks.append('\n\n'.join(current))
            current = [para]
            current_size = para_size
        else:
            current.append(para)
            current_size += para_size

    if current:
        chunks.append('\n\n'.join(current))

    return chunks


def chunk_file(filepath: str, max_size_kb: int = 50) -> list:
    """
    读取文件，如果小于 max_size_kb 返回 [整个内容]。
    否则按标题分段，并在每个 chunk 开头加注释和 frontmatter。

    返回 chunk 字符串列表。
    """
    path = Path(filepath)
    content = path.read_text(encoding='utf-8')
    max_bytes = max_size_kb * 1024

    if len(content.encode('utf-8')) <= max_bytes:
        return [content]

    frontmatter, body = _extract_frontmatter(content)

    # 先按 ## 标题分段
    sections = _split_by_headings(body)

    # 如果单个 section 还是太大，继续按段落分割
    refined = []
    for section in sections:
        if len(section.encode('utf-8')) > max_bytes:
            refined.extend(_split_by_paragraphs(section, max_bytes))
        else:
            refined.append(section)

    # 过滤空段
    refined = [s for s in refined if s.strip()]

    if not refined:
        return [content]

    filename = path.name
    total = len(refined)
    chunks = []

    for i, section in enumerate(refined, 1):
        header = f'<!-- chunk {i}/{total} of {filename} -->\n'
        if frontmatter:
            chunk = f'{frontmatter}\n{header}\n{section}'
        else:
            chunk = f'{header}\n{section}'
        chunks.append(chunk)

    return chunks
