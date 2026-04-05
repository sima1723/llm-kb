#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频/音频输入工具 — 提取 YouTube 字幕（或 Whisper 转录）并保存为
raw/media-notes/ 下带 frontmatter 的 Markdown 文件。

依赖（按优先级尝试）：
  pip install yt-dlp           # YouTube 字幕/元数据（强烈推荐）
  pip install openai-whisper   # 本地音频转文字（可选，较重）

用法：
  python tools/video_to_md.py "https://youtube.com/watch?v=..."
  python tools/video_to_md.py "https://youtube.com/watch?v=..." --whisper
  python tools/video_to_md.py "https://youtube.com/watch?v=..." --stub-only
"""

import re
import sys
import json
import shutil
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path

import click

try:
    from rich.console import Console
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_HERE = Path(__file__).resolve().parent.parent
console = Console() if HAS_RICH else None


def _log(msg: str, style: str = ""):
    if console:
        console.print(msg, style=style or None)
    else:
        print(msg)


def _slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text).strip()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug[:max_len].strip("-") or "untitled"


def _check_yt_dlp() -> bool:
    return shutil.which("yt-dlp") is not None


def _check_whisper() -> bool:
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _get_video_info(url: str) -> dict:
    """
    用 yt-dlp 获取视频元数据（不下载视频）。
    返回字典包含 title, channel, upload_date, webpage_url, description 等。
    """
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-playlist", url],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp 获取元数据失败：{result.stderr[:200]}")
    return json.loads(result.stdout)


def _get_subtitles(url: str, tmpdir: Path, lang: str = "zh") -> str:
    """
    尝试下载字幕（优先手动字幕，退而自动字幕）。
    返回字幕文本，失败返回空字符串。
    langs 优先级：zh > zh-Hans > zh-Hant > en
    """
    lang_candidates = [lang, "zh-Hans", "zh-Hant", "zh-CN", "en"]

    for sub_flag in ["--write-subs", "--write-auto-subs"]:
        for sub_lang in lang_candidates:
            result = subprocess.run(
                [
                    "yt-dlp",
                    sub_flag,
                    "--sub-lang", sub_lang,
                    "--sub-format", "vtt",
                    "--skip-download",
                    "--no-playlist",
                    "-o", str(tmpdir / "subtitle"),
                    url,
                ],
                capture_output=True, text=True, timeout=60
            )
            # 查找生成的 .vtt 文件
            vtt_files = list(tmpdir.glob("*.vtt"))
            if vtt_files:
                raw_vtt = vtt_files[0].read_text(encoding="utf-8", errors="ignore")
                return _parse_vtt(raw_vtt)

    return ""


def _parse_vtt(vtt: str) -> str:
    """
    将 WebVTT 字幕转为纯文本，去除时间戳行和重复行。
    """
    lines = vtt.splitlines()
    text_lines = []
    seen = set()

    for line in lines:
        line = line.strip()
        # 跳过时间戳行（如 00:00:01.000 --> 00:00:03.000）
        if re.match(r'^\d{2}:\d{2}:\d{2}', line):
            continue
        # 跳过 WEBVTT 头、空行、数字序号
        if not line or line == "WEBVTT" or line.isdigit():
            continue
        # 去除 HTML 标签（yt 字幕含 <c> 等）
        clean = re.sub(r'<[^>]+>', '', line).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        text_lines.append(clean)

    return "\n".join(text_lines)


def _transcribe_with_whisper(url: str, tmpdir: Path, model: str = "base") -> str:
    """
    用 yt-dlp 下载音频，再用 Whisper 转录。
    """
    import whisper

    audio_path = tmpdir / "audio.mp3"
    _log("  下载音频中（仅音轨）...")
    result = subprocess.run(
        [
            "yt-dlp",
            "--extract-audio", "--audio-format", "mp3",
            "--no-playlist",
            "-o", str(audio_path),
            url,
        ],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0 or not audio_path.exists():
        raise RuntimeError(f"音频下载失败：{result.stderr[:200]}")

    _log(f"  Whisper 转录中（模型：{model}）...")
    whisper_model = whisper.load_model(model)
    result_obj = whisper_model.transcribe(str(audio_path))
    return result_obj.get("text", "")


def _build_markdown(info: dict, transcript: str, url: str, source: str) -> tuple[str, str]:
    """
    构建 frontmatter + Markdown 正文。
    返回 (filename, full_content)。
    """
    title = info.get("title", "未知标题")
    channel = info.get("channel") or info.get("uploader", "未知频道")
    upload_date = info.get("upload_date", "")
    description = (info.get("description") or "")[:500]
    duration = info.get("duration", 0)
    duration_str = f"{int(duration)//60}:{int(duration)%60:02d}" if duration else "未知"

    # 格式化日期
    pub_date = ""
    if upload_date and len(upload_date) == 8:
        pub_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    else:
        pub_date = datetime.now().strftime("%Y-%m-%d")

    today = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify(title)
    filename = f"{today}-{slug}.md"

    # frontmatter
    frontmatter = (
        "---\n"
        f"source_type: {source}\n"
        f"source_url: {url}\n"
        f"title: \"{title}\"\n"
        f"channel: \"{channel}\"\n"
        f"published_at: {pub_date}\n"
        f"duration: {duration_str}\n"
        f"clipped_at: {today}\n"
        "---\n\n"
    )

    # 正文
    body_parts = [f"# {title}\n"]
    body_parts.append(f"**频道**：{channel}  |  **发布**：{pub_date}  |  **时长**：{duration_str}\n")
    body_parts.append(f"**来源**：{url}\n")

    if description:
        body_parts.append(f"\n## 简介\n\n{description}\n")

    if transcript:
        body_parts.append(f"\n## 字幕 / 转录\n\n{transcript}\n")
    else:
        body_parts.append(
            "\n## 笔记\n\n"
            "> ⚠️ 未能自动提取字幕，请手动填写笔记。\n\n"
            "（在此填写核心观点、时间戳摘要等）\n"
        )

    body_parts.append(
        "\n## 关键观点\n\n"
        "（编译后由 LLM 自动提取，或手动填写）\n"
    )

    body = "\n".join(body_parts)
    return filename, frontmatter + body


# ─── CLI ────────────────────────────────────────────────────────────────────

@click.command()
@click.argument("url")
@click.option("--output", default=None, help="输出目录（默认：raw/media-notes/）")
@click.option("--lang", default="zh", show_default=True, help="字幕语言代码")
@click.option("--whisper", "use_whisper", is_flag=True, help="强制用 Whisper 转录（跳过字幕尝试）")
@click.option("--whisper-model", default="base", show_default=True,
              help="Whisper 模型大小：tiny/base/small/medium/large")
@click.option("--stub-only", is_flag=True, help="只生成 stub（不提取字幕/转录）")
def main(url: str, output: str, lang: str, use_whisper: bool,
         whisper_model: str, stub_only: bool):
    """
    从 YouTube（或其他 yt-dlp 支持的平台）提取字幕/转录，
    保存为 raw/media-notes/ 下的 Markdown 文件。
    """
    output_dir = Path(output) if output else _HERE / "raw" / "media-notes"
    output_dir.mkdir(parents=True, exist_ok=True)

    has_ytdlp = _check_yt_dlp()
    has_whisper = _check_whisper()

    if not has_ytdlp and not stub_only:
        _log(
            "[yellow]⚠ 未检测到 yt-dlp，将只生成 stub 笔记模板。\n"
            "  安装方法：pip install yt-dlp[/yellow]"
        )
        stub_only = True

    # 获取视频元数据
    info = {}
    if has_ytdlp:
        _log(f"获取视频信息：{url}")
        try:
            info = _get_video_info(url)
            _log(f"  标题：{info.get('title', '(未知)')}", "dim")
        except Exception as e:
            _log(f"[yellow]⚠ 元数据获取失败（{e}），将用 URL 生成文件名[/yellow]")

    # 确定来源类型（youtube / podcast / etc.）
    if "youtube.com" in url or "youtu.be" in url:
        source_type = "youtube"
    elif any(x in url for x in ("podcast", "spotify", "anchor")):
        source_type = "podcast"
    else:
        source_type = "media"

    transcript = ""

    if not stub_only:
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = Path(tmpdir_str)

            if use_whisper:
                if has_whisper:
                    _log("使用 Whisper 转录...")
                    try:
                        transcript = _transcribe_with_whisper(url, tmpdir, whisper_model)
                        _log(f"  ✓ 转录完成，{len(transcript)} 字符", "green")
                    except Exception as e:
                        _log(f"[red]✗ Whisper 转录失败：{e}[/red]")
                else:
                    _log("[yellow]⚠ openai-whisper 未安装，跳过转录\n  安装：pip install openai-whisper[/yellow]")
            else:
                # 优先尝试字幕
                _log(f"尝试提取字幕（语言：{lang}）...")
                try:
                    transcript = _get_subtitles(url, tmpdir, lang)
                    if transcript:
                        _log(f"  ✓ 字幕提取成功，{len(transcript)} 字符", "green")
                    else:
                        _log("  未找到字幕", "yellow")
                        # 如果 Whisper 可用，自动降级
                        if has_whisper:
                            _log("  自动降级到 Whisper 转录...")
                            transcript = _transcribe_with_whisper(url, tmpdir, whisper_model)
                            _log(f"  ✓ 转录完成，{len(transcript)} 字符", "green")
                        else:
                            _log("  [dim]提示：安装 openai-whisper 可自动转录音频[/dim]")
                except Exception as e:
                    _log(f"[yellow]⚠ 字幕提取失败：{e}[/yellow]")

    # 生成 Markdown
    filename, content = _build_markdown(info, transcript, url, source_type)
    output_path = output_dir / filename
    output_path.write_text(content, encoding="utf-8")

    _log(f"\n[green]✓ 已保存：{output_path}[/green]")
    _log(f"  字幕/转录：{'✓' if transcript else '✗（请手动填写）'}")
    _log(f"  下一步：运行 [cyan]make compile[/cyan] 编译此文件到 wiki")


if __name__ == "__main__":
    main()
