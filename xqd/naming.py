"""文件名规范 —— 对应 C# `Xqd.Core.Naming`（唯一事实来源，两套实现必须一致）。

规则要点：
  · 只替换 ASCII 非法字符；全角冒号「：」保留（课名里常见，删了会丢信息）。
  · Windows 保留设备名（CON/PRN/COM1…）前加下划线。
  · 成品名 =「序号.课名.日期.扩展名」，**不加 -1 / -2 后缀**：
    重名的正确处理是「已有完整成品→跳过；残件→删掉覆盖重下」。
  · ffmpeg 临时输出必须以 .mp4 结尾（.part 结尾 ffmpeg 认不出封装格式）。
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def safe_name(name: str) -> str:
    if not name:
        return "未命名"
    s = ILLEGAL.sub("_", name).strip().rstrip(".")
    if s.upper() in RESERVED:
        s = "_" + s
    return s or "未命名"


def fmt_date(ms: int) -> str:
    """startTime 毫秒 → YYYY.MM.DD（本地时区）。"""
    if ms <= 0:
        return ""
    try:
        return _dt.datetime.fromtimestamp(ms / 1000).strftime("%Y.%m.%d")
    except Exception:
        return ""


def fmt_when(ms: int) -> str:
    """startTime 毫秒 → MM.DD HH:MM（界面卡片格式）。"""
    if ms <= 0:
        return ""
    try:
        return _dt.datetime.fromtimestamp(ms / 1000).strftime("%m.%d %H:%M")
    except Exception:
        return ""


def lesson_stem(seq: int, title: str, when_date: str = "") -> str:
    """成品文件主名：<序号>.<课名>.<日期>（不含扩展名）。"""
    parts = [f"{seq}.{safe_name(title)}"]
    if when_date:
        parts.append(when_date)
    return ".".join(parts)


def expected_ext(lesson_type: str = "") -> str:
    """AUDIO 保持原始音频容器，其余统一 MP4。"""
    return ".mp3" if (lesson_type or "").upper() == "AUDIO" else ".mp4"


def course_filename(seq: int, title: str, when_date: str = "",
                    lesson_type: str = "", ext: str = "") -> str:
    return lesson_stem(seq, title, when_date) + (ext or expected_ext(lesson_type))


def camp_folder(camp_name: str) -> str:
    """营目录名 —— 下载与「已下载检测」必须用同一个，否则扫描永远找不到。"""
    return safe_name(camp_name)


def temp_part_path(out_path: str | Path) -> Path:
    p = Path(out_path)
    stem = p.name[:-4] if p.name.lower().endswith(".mp4") else p.name
    return p.with_name(stem + ".part.mp4")


def index_name() -> str:
    return ".xqd_index.json"
