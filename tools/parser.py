#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML 响应解析器：从 LLM 输出中提取 <wiki_entry> 标签内容。
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _clean_content(content: str) -> str:
    """清理 content：合并连续3个以上空行为2个。"""
    content = content.strip()
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content


def _extract_tag(text: str, tag: str) -> Optional[str]:
    """从文本中提取单个标签的内容（非贪婪）。"""
    pattern = rf'<{tag}>(.*?)</{tag}>'
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else None


def parse_wiki_entries(response: str) -> list:
    """
    从 LLM 响应中解析 <wiki_entry> 标签。

    返回：[{"filename": "xxx.md", "action": "create|update", "content": "..."}]

    容错处理：
    - 如果 XML 格式不完整，尝试逐个 <wiki_entry> 提取
    - 如果完全无法解析，返回空列表并记录原始响应
    - 清理 content 中的多余空行（连续3个以上合并为2个）
    """
    entries = []

    # 提取所有 <wiki_entry>...</wiki_entry> 块
    pattern = r'<wiki_entry>(.*?)</wiki_entry>'
    blocks = re.findall(pattern, response, re.DOTALL)

    if not blocks:
        # 尝试宽松匹配（标签可能有属性或格式稍有偏差）
        pattern_loose = r'<wiki_entry\b[^>]*>(.*?)</wiki_entry>'
        blocks = re.findall(pattern_loose, response, re.DOTALL)

    if not blocks:
        logger.warning("无法从响应中解析 <wiki_entry> 块，原始响应长度: %d", len(response))
        logger.debug("原始响应前500字符: %s", response[:500])
        return []

    for block in blocks:
        filename = _extract_tag(block, 'filename')
        action = _extract_tag(block, 'action')
        content = _extract_tag(block, 'content')

        if not filename:
            logger.warning("wiki_entry 缺少 <filename>，跳过该条目")
            continue

        # action 默认为 create
        if not action:
            action = 'create'
        action = action.strip().lower()
        if action not in ('create', 'update'):
            action = 'create'

        # content 可为空（如纯 stub）
        if content is None:
            content = ''

        entries.append({
            'filename': filename,
            'action': action,
            'content': _clean_content(content),
        })

    return entries


def parse_unfixable(response: str) -> list:
    """
    从 lint_ai 响应中解析 <unfixable> 标签。
    返回：[{"filename": "xxx.md", "reason": "..."}]
    """
    results = []
    pattern = r'<unfixable>(.*?)</unfixable>'
    blocks = re.findall(pattern, response, re.DOTALL)
    for block in blocks:
        filename = _extract_tag(block, 'filename')
        reason = _extract_tag(block, 'reason')
        if filename:
            results.append({'filename': filename, 'reason': reason or '未说明'})
    return results
