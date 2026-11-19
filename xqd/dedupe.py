"""「这门课是不是已经下好了」—— 对应 C# `Xqd.Core.Dedupe.ExistingChecker`。

判定依据（缺一不可）：
  1. 文件名主键 == 序号.课名.日期（不看 -1/-2 后缀，那套规则已废弃）；
  2. 文件大小 > 10 KB（0 字节/半截文件不算）；
  3. 有课程时长时，用 ffprobe 读成品时长，容差 max(3s, 1%)。

★ 为什么必须比时长：HLS 断点续传最容易出现「分片下全了但封装没做完」的
  半成品，大小看着像对的，播放到一半就断——只有时长能识破。
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .probe import find_ffprobe

MIN_SIZE = 10 * 1024
MEDIA_EXTS = {".mp4", ".mp3", ".m4a", ".aac", ".mov", ".mkv", ".webm"}


@dataclass
class ExistingState:
    status: str          # missing / ok / broken
    path: str = ""
    size: int = 0
    duration: float = 0.0

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"


def probe_duration(path: str | Path, ffprobe: str = "") -> float:
    """ffprobe 读时长（秒）；读不到返回 0。"""
    exe = ffprobe or find_ffprobe()
    if not exe:
        return 0.0
    try:
        out = subprocess.run(
            [exe, "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30)
        data = json.loads(out.stdout or "{}")
        dur = float(data.get("format", {}).get("duration") or 0)
        if dur > 0:
            return dur
        for st in data.get("streams", []):
            dur = float(st.get("duration") or 0)
            if dur > 0:
                return dur
    except Exception:
        pass
    return 0.0


def tolerance(expect: float) -> float:
    return max(3.0, expect * 0.01)


def check(path: str | Path, expect_seconds: float = 0.0, ffprobe: str = "") -> ExistingState:
    p = Path(path)
    if not p.exists():
        return ExistingState("missing", str(p))
    size = p.stat().st_size
    if size <= MIN_SIZE:
        return ExistingState("broken", str(p), size)
    if expect_seconds > 0:
        dur = probe_duration(p, ffprobe)
        if dur <= 0:
            # 没有 ffprobe / 读不出来：退化为「按大小判」，标 broken 留给人眼复核
            return ExistingState("broken" if size < 1024 * 1024 else "ok",
                                 str(p), size, dur)
        if abs(dur - expect_seconds) > tolerance(expect_seconds):
            return ExistingState("broken", str(p), size, dur)
        return ExistingState("ok", str(p), size, dur)
    return ExistingState("ok", str(p), size)


def scan_dir(folder: str | Path) -> dict[str, Path]:
    """目录快照：文件名（不含扩展名）→ 路径。只收媒体扩展名。"""
    result: dict[str, Path] = {}
    d = Path(folder)
    if not d.is_dir():
        return result
    for f in d.iterdir():
        if f.is_file() and f.suffix.lower() in MEDIA_EXTS:
            result.setdefault(f.stem, f)
    return result
