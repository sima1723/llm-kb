#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动笔记模板生成器：在 raw/ 对应子目录创建带 frontmatter 的空白笔记。
用法：
  python tools/new_note.py "笔记标题" [--type article|paper|media-note]
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

TYPE_DIRS = {
    "article": "raw/articles",
    "paper": "raw/papers",
    "media-note": "raw/media-notes",
    "repo": "raw/repos",
}

TEMPLATES = {
    "article": """\
---
source_type: article
title: "{title}"
source_url: ""
created_at: {date}
tags: []
---

# {title}

## 摘要


## 关键要点


## 详细笔记


## 个人思考


""",
    "paper": """\
---
source_type: paper
title: "{title}"
authors: []
year: {year}
venue: ""
source_url: ""
created_at: {date}
tags: []
---

# {title}

## 摘要


## 核心贡献


## 方法


## 实验结果


## 局限性


## 个人评价


""",
    "media-note": """\
---
source_type: media-note
title: "{title}"
media_type: ""  # video | podcast | talk | course
source_url: ""
creator: ""
created_at: {date}
tags: []
---

# {title}

## 一句话总结


## 关键洞察


## 精彩片段


## 行动建议


""",
    "repo": """\
---
source_type: repo
title: "{title}"
repo_url: ""
language: ""
created_at: {date}
tags: []
---

# {title}

## 项目简介


## 核心架构


## 关键实现


## 使用方法


## 值得学习的点


""",
}


def title_to_filename(title: str, date: str) -> str:
    """将标题转为安全的文件名。"""
    # 保留中文、字母、数字、连字符
    import re
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title)
    safe = safe.replace(' ', '-').strip('-')
    return f"{date}-{safe}.md"


def main():
    parser = argparse.ArgumentParser(
        description="在 raw/ 目录创建带 frontmatter 的笔记模板",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            '  python tools/new_note.py "注意力机制" --type paper\n'
            '  python tools/new_note.py "Andrej Karpathy讲座笔记" --type media-note'
        ),
    )
    parser.add_argument("title", help="笔记标题")
    parser.add_argument(
        "--type",
        choices=list(TYPE_DIRS.keys()),
        default="article",
        help="笔记类型（默认：article）",
    )
    parser.add_argument(
        "--no-edit",
        action="store_true",
        help="创建后不打开编辑器",
    )
    args = parser.parse_args()

    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    year = now.strftime("%Y")

    # 确定输出目录
    output_dir = Path(TYPE_DIRS[args.type])
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    filename = title_to_filename(args.title, date)
    output_path = output_dir / filename

    if output_path.exists():
        print(f"文件已存在：{output_path}")
        print("提示：请直接编辑已有文件，或换一个标题。")
        sys.exit(1)

    # 生成内容
    template = TEMPLATES.get(args.type, TEMPLATES["article"])
    content = template.format(title=args.title, date=date, year=year)

    output_path.write_text(content, encoding="utf-8")

    print(f"✓ 已创建：{output_path}")
    print(f"  类型：{args.type}")
    print(f"  路径：{output_path.absolute()}")

    # 尝试用编辑器打开
    if not args.no_edit:
        editor = os.environ.get("EDITOR", "")
        if editor:
            try:
                subprocess.run([editor, str(output_path)])
            except Exception:
                pass
        else:
            print(f"\n提示：设置 $EDITOR 环境变量后，下次会自动打开编辑器。")
            print(f"  例如：export EDITOR=vim")


if __name__ == "__main__":
    main()
