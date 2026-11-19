"""分片拼接 + 封装 —— 对应 C# `Xqd.Core.Engine.Muxer`。

★ 必须「按字节 cat 成 all.ts」再喂 ffmpeg，不能用 concat demuxer：
  concat demuxer 会重置时间戳，实测成品只有 6 秒（230.8s vs 224.6s），时长校验必挂。
★ 临时输出必须以 .mp4 结尾，否则 ffmpeg 报 "Error initializing the muxer"。
★ 分片文件名 %05d_ 前缀保证「字典序 == 数值序」，按名字排序即播放顺序。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .naming import temp_part_path
from .probe import find_ffmpeg


def _segments(seg_dir: Path) -> list[Path]:
    segs = [p for p in seg_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".ts" and not p.name.lower().startswith("all.")]
    return sorted(segs, key=lambda p: p.name)


def concat_bytes(seg_dir: str | Path, cat_name: str = "all.ts") -> tuple[Path | None, int]:
    """按序拼接分片；返回 (all.ts 路径, 字节数)。排除上一次失败残留的 all.*。"""
    seg_dir = Path(seg_dir)
    segs = _segments(seg_dir)
    if not segs:
        return None, 0
    cat = seg_dir / cat_name
    total = 0
    with open(cat, "wb") as out:
        for seg in segs:
            with open(seg, "rb") as f:
                data = f.read()
            out.write(data)
            total += len(data)
    return cat, total


def mux_copy(all_ts: str | Path, out_path: str | Path, ffmpeg: str = "") -> tuple[bool, str]:
    """ffmpeg -c copy 转封装到 out.part.mp4，成功后原子改名成正式文件。"""
    exe = ffmpeg or find_ffmpeg()
    if not exe:
        return False, "找不到 ffmpeg —— 先跑 tools/probe_env.py 看环境，或装到 ~/.xqd_tool/ffmpeg/bin"
    tmp = temp_part_path(out_path)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [exe, "-y", "-hide_banner", "-loglevel", "error",
             "-i", str(all_ts), "-c", "copy", "-bsf:a", "aac_adtstoasc", str(tmp)],
            capture_output=True, text=True, timeout=3600)
    except Exception as exc:
        return False, f"ffmpeg 调用失败：{exc}"
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        return False, "ffmpeg 转封装失败：" + (" | ".join(tail) if tail else f"code={proc.returncode}")
    os.replace(tmp, out_path)
    return True, "封装完成"


def cleanup(seg_dir: str | Path) -> None:
    """逐个删分片与 all.ts（一次性批量删会撞安全删除阈值）。跳过 .part.mp4。"""
    seg_dir = Path(seg_dir)
    if not seg_dir.is_dir():
        return
    for p in seg_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() in (".ts", ".mp4") and not p.name.lower().endswith(".part.mp4"):
            try:
                p.unlink()
            except Exception:
                pass
