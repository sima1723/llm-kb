#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
状态管理模块：记录已处理文件、断点续做、防并发。
"""

import json
import hashlib
import os
import fcntl
from pathlib import Path
from datetime import datetime
from typing import Optional


class StateManager:
    """管理编译状态：断点续做、增量检测、费用记录。"""

    def __init__(self, state_dir: str = ".state"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.checkpoints_file = self.state_dir / "checkpoints.json"
        self.processed_file = self.state_dir / "processed_files.json"
        self.compile_log_file = self.state_dir / "compile_log.json"
        self.errors_dir = self.state_dir / "compile_errors"
        self.errors_dir.mkdir(exist_ok=True)

        # 初始化文件
        for f in [self.checkpoints_file, self.processed_file, self.compile_log_file]:
            if not f.exists():
                f.write_text("{}")

    # ── 文件锁辅助 ───────────────────────────────────────────────

    def _read_json(self, path: Path) -> dict:
        """加锁读取 JSON 文件。"""
        with open(path, "r", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                content = fh.read().strip()
                return json.loads(content) if content else {}
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _write_json(self, path: Path, data: dict):
        """加锁写入 JSON 文件。"""
        with open(path, "w", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ── 断点管理 ────────────────────────────────────────────────

    def get_checkpoint(self, phase: str) -> Optional[dict]:
        """获取某阶段的断点数据，不存在返回 None。"""
        data = self._read_json(self.checkpoints_file)
        return data.get(phase)

    def set_checkpoint(self, phase: str, data: dict):
        """设置某阶段的断点数据。"""
        all_data = self._read_json(self.checkpoints_file)
        all_data[phase] = {
            **data,
            "_updated_at": datetime.now().isoformat()
        }
        self._write_json(self.checkpoints_file, all_data)

    def clear_checkpoint(self, phase: str):
        """清除某阶段的断点（完成后调用）。"""
        all_data = self._read_json(self.checkpoints_file)
        all_data.pop(phase, None)
        self._write_json(self.checkpoints_file, all_data)

    # ── 已处理文件管理 ──────────────────────────────────────────

    def get_processed_files(self) -> dict:
        """
        返回所有已处理文件的记录。
        格式：{filepath: {hash, outputs, processed_at}}
        """
        return self._read_json(self.processed_file)

    def mark_file_processed(self, filepath: str, hash: str, outputs: list):
        """标记文件为已处理。"""
        data = self._read_json(self.processed_file)
        data[filepath] = {
            "hash": hash,
            "outputs": outputs,
            "processed_at": datetime.now().isoformat()
        }
        self._write_json(self.processed_file, data)

    def is_file_processed(self, filepath: str) -> bool:
        """
        判断文件是否已处理（通过 hash 比较）。
        如果文件内容变化（hash 不同），视为未处理。
        """
        data = self._read_json(self.processed_file)
        if filepath not in data:
            return False
        stored_hash = data[filepath].get("hash", "")
        current_hash = self.file_hash(filepath)
        return stored_hash == current_hash

    def get_unprocessed_files(self, raw_dir: str) -> list:
        """
        扫描 raw_dir 下所有 .md 文件，返回新增或修改的文件列表。
        """
        raw_path = Path(raw_dir)
        all_md = list(raw_path.rglob("*.md"))
        unprocessed = []
        for f in sorted(all_md):
            fp = str(f)
            if not self.is_file_processed(fp):
                unprocessed.append(fp)
        return unprocessed

    # ── 文件哈希 ────────────────────────────────────────────────

    def file_hash(self, filepath: str) -> str:
        """计算文件 sha256（文件不存在返回空字符串）。"""
        try:
            h = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except FileNotFoundError:
            return ""

    # ── 错误记录 ────────────────────────────────────────────────

    def record_error(self, filepath: str, error: str):
        """记录某文件的编译错误。"""
        safe_name = Path(filepath).name + ".txt"
        error_file = self.errors_dir / safe_name
        with open(error_file, "w", encoding="utf-8") as f:
            f.write(f"File: {filepath}\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"Error:\n{error}\n")

    def get_error_files(self) -> list:
        """返回有编译错误的文件列表。"""
        return [
            f.stem  # 去掉 .txt 后缀
            for f in self.errors_dir.iterdir()
            if f.suffix == ".txt"
        ]

    # ── 费用日志 ────────────────────────────────────────────────

    def append_compile_log(self, entry: dict):
        """追加一条编译日志（含费用）。"""
        data = self._read_json(self.compile_log_file)
        logs = data.get("logs", [])
        logs.append({**entry, "logged_at": datetime.now().isoformat()})
        data["logs"] = logs
        self._write_json(self.compile_log_file, data)

    def get_total_cost(self) -> float:
        """汇总所有编译日志的累计费用。"""
        data = self._read_json(self.compile_log_file)
        return sum(e.get("cost_usd", 0) for e in data.get("logs", []))
