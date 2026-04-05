#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目初始化脚本 — 由 `make init` 调用。
检查环境、安装依赖、创建目录、初始化状态文件。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent

REQUIRED_DIRS = [
    "raw/articles",
    "raw/papers",
    "raw/repos",
    "raw/media-notes",
    "wiki/answers",
    "wiki/slides",
    "tools",
    "templates",
    ".state",
]

REQUIRED_STATE_FILES = [
    ".state/processed_files.json",
    ".state/checkpoints.json",
]


def check_python_version():
    """检查 Python 版本 >= 3.10"""
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        print(f"✗ Python {major}.{minor} 不满足要求（需要 >= 3.10）")
        sys.exit(1)
    print(f"✓ Python {major}.{minor}")


def install_requirements():
    """pip install -r requirements.txt"""
    req_file = _HERE / "requirements.txt"
    if not req_file.exists():
        print("✗ requirements.txt 不存在")
        return
    print("→ 安装 Python 依赖...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"],
        cwd=str(_HERE),
    )
    if result.returncode == 0:
        print("✓ 依赖安装完成")
    else:
        print("✗ 依赖安装失败，请手动运行: pip install -r requirements.txt")


def create_directories():
    """创建所有必要目录"""
    for d in REQUIRED_DIRS:
        p = _HERE / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            print(f"  创建目录: {d}")
    # tools/__init__.py
    init_file = _HERE / "tools" / "__init__.py"
    if not init_file.exists():
        init_file.write_text("# tools package\n")
    print("✓ 目录结构就绪")


def init_state_files():
    """初始化 .state/ 文件"""
    for fname in REQUIRED_STATE_FILES:
        fpath = _HERE / fname
        if not fpath.exists():
            fpath.write_text("{}\n", encoding="utf-8")
            print(f"  初始化: {fname}")
    print("✓ 状态文件就绪")


def check_api_key():
    """检查 ANTHROPIC_API_KEY"""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key and key.startswith("sk-"):
        print(f"✓ ANTHROPIC_API_KEY 已设置（{key[:10]}...）")
    else:
        print("⚠  未设置 ANTHROPIC_API_KEY，编译和问答功能需要此环境变量")
        print("   export ANTHROPIC_API_KEY=sk-ant-...")


def init_git():
    """初始化 git 仓库（如果尚未初始化）"""
    git_dir = _HERE / ".git"
    if git_dir.exists():
        print("✓ git 仓库已存在")
        return
    result = subprocess.run(
        ["git", "init"],
        cwd=str(_HERE),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("✓ git 仓库已初始化")
    else:
        print("⚠  git init 失败，请手动初始化")


def print_welcome():
    """打印欢迎信息和下一步指引"""
    print()
    print("=" * 50)
    print("  LLM Knowledge Base 初始化完成！")
    print("=" * 50)
    print()
    print("下一步：")
    print("  1. 确保设置了 ANTHROPIC_API_KEY")
    print("  2. 往 raw/ 中放入资料：")
    print("       make clip URL=https://...      # 抓取网页")
    print("       make note TITLE='我的笔记'     # 新建笔记")
    print("  3. 编译知识库：")
    print("       make compile")
    print("  4. 搜索和提问：")
    print("       make search Q='关键词'")
    print("       make ask-save Q='你的问题'")
    print()
    print("  make help 查看所有命令")
    print()


def main():
    print("\n🚀 初始化 LLM Knowledge Base...\n")
    check_python_version()
    install_requirements()
    create_directories()
    init_state_files()
    check_api_key()
    init_git()
    print_welcome()


if __name__ == "__main__":
    main()
