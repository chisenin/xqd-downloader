"""工具探测 —— 对应 C# `Xqd.Core.Setup.ToolLocator`。

★ 换机器跑不起来的两大元凶，都在这里解决：
  1. ffmpeg 装在作者本机某个固定目录 → 新机器必然找不到。
     查找顺序：自装目录 → 用户点选记录（tools.json）→ 环境变量 → PATH。
  2. MuMu 模拟器装在 D 盘某处 → 新机器路径全变。
     查找顺序：点选记录 → 环境变量 → 常见安装目录 → 各固定盘浅层搜索 → PATH。

所有结果都能「记下来」（remember_*），下次直接命中，不再重复搜盘。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config


# ── 用户点选记录 ──────────────────────────────────────────────────────

def _tools_file() -> Path:
    return config.tool_dir() / "tools.json"


def _load_tools() -> dict:
    try:
        return json.loads(_tools_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_tools(data: dict) -> bool:
    try:
        _tools_file().parent.mkdir(parents=True, exist_ok=True)
        _tools_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def remember_ffmpeg_dir(bin_dir: str) -> bool:
    """记住用户指定的 ffmpeg bin 目录（必须先验证里面真有 ffmpeg.exe）。"""
    exe = Path(bin_dir) / "ffmpeg.exe"
    if not exe.exists():
        return False
    data = _load_tools()
    data["ffmpeg_dir"] = str(Path(bin_dir))
    return _save_tools(data)


def remember_mumu_manager(manager_path: str) -> bool:
    name = Path(manager_path).name.lower()
    if name != "mumumanager.exe" or not Path(manager_path).exists():
        return False
    data = _load_tools()
    data["mumu_manager"] = str(Path(manager_path))
    return _save_tools(data)


# ── ffmpeg / ffprobe ──────────────────────────────────────────────────

def _from_path(name: str) -> str:
    return shutil.which(name) or shutil.which(name + ".exe") or ""


def find_ffmpeg() -> str:
    """自装目录 → 点选记录 → XQD_FFMPEG_DIR → PATH。"""
    p = config.ffmpeg_tool_dir() / "ffmpeg.exe"
    if p.exists():
        return str(p)

    rec = _load_tools().get("ffmpeg_dir", "")
    if rec and (Path(rec) / "ffmpeg.exe").exists():
        return str(Path(rec) / "ffmpeg.exe")

    env = os.environ.get("XQD_FFMPEG_DIR", "").strip()
    if env and (Path(env) / "ffmpeg.exe").exists():
        return str(Path(env) / "ffmpeg.exe")

    return _from_path("ffmpeg")


def find_ffprobe() -> str:
    p = config.ffmpeg_tool_dir() / "ffprobe.exe"
    if p.exists():
        return str(p)

    rec = _load_tools().get("ffmpeg_dir", "")
    if rec and (Path(rec) / "ffprobe.exe").exists():
        return str(Path(rec) / "ffprobe.exe")

    env = os.environ.get("XQD_FFMPEG_DIR", "").strip()
    if env and (Path(env) / "ffprobe.exe").exists():
        return str(Path(env) / "ffprobe.exe")

    return _from_path("ffprobe")


# ── MuMu 模拟器 ──────────────────────────────────────────────────────

_MUMU_REL_DIRS = [
    "Netease\\MuMu",
    "Netease\\MuMuPlayer-12.0",
    "Program Files\\Netease\\MuMu",
    "Program Files\\Netease\\MuMuPlayer-12.0",
]


def find_mumu_manager() -> str:
    """点选记录 → XQD_MUMU_MANAGER → XQD_MUMU_HOME → 常见目录 → 固定盘浅搜 → PATH。"""
    rec = _load_tools().get("mumu_manager", "")
    if rec and Path(rec).exists():
        return rec

    env = os.environ.get("XQD_MUMU_MANAGER", "").strip()
    if env and Path(env).exists():
        return env

    home = os.environ.get("XQD_MUMU_HOME", "").strip()
    if home:
        for rel in ("nx_main\\MuMuManager.exe", "MuMuManager.exe"):
            p = Path(home) / rel
            if p.exists():
                return str(p)

    roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
             os.environ.get("ProgramW6432", r"C:\Program Files"),
             os.environ.get("LOCALAPPDATA", "")]
    for root in roots:
        if not root:
            continue
        for rel in _MUMU_REL_DIRS:
            for sub in ("nx_main\\MuMuManager.exe", "MuMuManager.exe", "shell\\MuMuManager.exe"):
                p = Path(root) / rel / sub
                if p.exists():
                    return str(p)

    # 各固定盘浅层搜索（限深 2，避免全盘扫描）
    for letter in _drive_letters():
        base = Path(letter + ":\\")
        for rel in _MUMU_REL_DIRS:
            for sub in ("nx_main\\MuMuManager.exe", "MuMuManager.exe"):
                p = base / rel / sub
                if p.exists():
                    return str(p)

    return _from_path("MuMuManager")


def _drive_letters() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return [chr(65 + i) for i in range(26) if mask & (1 << i)]
    except Exception:
        return []


# ── adb / 设备 ────────────────────────────────────────────────────────

def find_adb() -> str:
    """点选记录 → XQD_ADB → MuMu 同级 adb.exe → PATH。"""
    rec = _load_tools().get("adb", "")
    if rec and Path(rec).exists():
        return rec

    env = os.environ.get("XQD_ADB", "").strip()
    if env and Path(env).exists():
        return env

    mumu = find_mumu_manager()
    if mumu:
        for rel in ("adb.exe", "..\\adb.exe", "shell\\adb.exe"):
            p = (Path(mumu).parent / rel).resolve()
            if p.exists():
                return str(p)

    return _from_path("adb")


def resolve_adb_device(adb_exe: str = "") -> str:
    """XQD_ADB_DEVICE 优先，否则 `adb devices` 取第一台在线设备。"""
    env = os.environ.get("XQD_ADB_DEVICE", "").strip()
    if env:
        return env

    adb = adb_exe or find_adb()
    if not adb:
        return ""
    try:
        out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10)
        for line in (out.stdout or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                return parts[0]
    except Exception:
        pass
    return ""


# ── 体检报告 ──────────────────────────────────────────────────────────

def report() -> list[dict]:
    """给 tools/probe_env.py 和 EnvCheckWindow 用的结构化结果（C# 侧同构）。"""
    ff, fp, mumu, adb = find_ffmpeg(), find_ffprobe(), find_mumu_manager(), find_adb()
    dev = resolve_adb_device(adb) if adb else ""
    return [
        {"name": "ffmpeg（分片转封装）", "path": ff, "required": True,
         "ok": bool(ff), "hint": "下载/合并成 MP4 必需；没装就合并不了"},
        {"name": "ffprobe（成品时长校验）", "path": fp, "required": True,
         "ok": bool(fp), "hint": "校验成品时长必需；没有就只能按大小判"},
        {"name": "MuMu 模拟器（抓授权）", "path": mumu, "required": False,
         "ok": bool(mumu), "hint": "抓授权曲库时必需；已有 cookie.txt 可跳过"},
        {"name": "adb（连模拟器）", "path": adb, "required": False,
         "ok": bool(adb), "hint": "跟 MuMu 一起用"},
        {"name": "在线设备", "path": dev, "required": False,
         "ok": bool(dev), "hint": "adb devices 里的第一台在线设备"},
    ]
