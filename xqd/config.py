"""配置与路径 —— 对应 C# `Xqd.Core.Config`。

★ 这里一条硬编码路径都没有：
  · 配置目录走用户主目录（`~/.xqd_tool`），可用 XQD_TEST_HOME 隔离；
  · 下载目录优先读 Windows 注册表里的「下载」Known Folder（用户可能重定向到别的盘），
    读不到才回落 `~/Downloads`；
  · 旧默认目录 `Z:\\太极营` 只作为「历史脏值」识别，本机不存在就回落。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ── 目录 ──────────────────────────────────────────────────────────────

def home_dir() -> Path:
    """用户主目录（Windows 上 USERPROFILE 比 Path.home() 更贴近资源管理器）。"""
    env = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    return Path(env) if env else Path.home()


def test_home() -> str:
    """测试隔离目录；只影响配置/历史/分片，**不影响凭据读取**。"""
    return os.environ.get("XQD_TEST_HOME", "")


def tool_dir() -> Path:
    th = test_home()
    return Path(th) if th else home_dir() / ".xqd_tool"


def config_file() -> Path:
    return tool_dir() / "config.json"


def history_file() -> Path:
    return tool_dir() / "history.json"


def parts_dir() -> Path:
    return tool_dir() / "parts"


def cred_file() -> Path:
    """凭据固定放真实用户目录，测试隔离也读得到（与 C# 一致）。"""
    return home_dir() / ".xqd_tool" / "cookie.txt"


def ffmpeg_tool_dir() -> Path:
    return tool_dir() / "ffmpeg" / "bin"


# ── 配置 ──────────────────────────────────────────────────────────────

DEFAULTS = {
    "out_dir": "",
    "auto_launch": True,
    "auto_close": True,
    "platform": "qianliao",
    "quality": "max",
    "mode": "api",
    "workers": 2,
    "seg_workers": 12,
}


def load_config(path: Path | None = None) -> dict:
    p = path or config_file()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        cfg = dict(DEFAULTS)
        if isinstance(data, dict):
            cfg.update({k: data[k] for k in data if k in DEFAULTS})
        return cfg
    except Exception:
        return dict(DEFAULTS)


def save_config(cfg: dict, path: Path | None = None) -> None:
    p = path or config_file()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        out = {k: cfg.get(k, v) for k, v in DEFAULTS.items()}
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:      # 配置写不了不该让主流程崩
        print(f"保存配置失败：{exc}", file=sys.stderr)


# ── 系统「下载」文件夹 ────────────────────────────────────────────────

_DOWNLOAD_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"


def windows_download_dir() -> Path:
    """读 HKCU\\...\\User Shell Folders 的下载项（可被重定向到 D:\\download）。"""
    if sys.platform == "win32":
        try:
            import ctypes
            import ctypes.wintypes as wt

            hkey = wt.HKEY()
            advapi = ctypes.windll.advapi32
            if advapi.RegOpenKeyExW(
                ctypes.c_void_p(0x80000001),  # HKEY_CURRENT_USER
                "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders",
                0, 0x20019, ctypes.byref(hkey)) == 0:
                try:
                    size, typ = wt.DWORD(), wt.DWORD()
                    advapi.RegQueryValueExW(hkey, _DOWNLOAD_GUID, None,
                                            ctypes.byref(typ), None, ctypes.byref(size))
                    if size.value:
                        buf = ctypes.create_unicode_buffer(size.value // 2 + 1)
                        if advapi.RegQueryValueExW(hkey, _DOWNLOAD_GUID, None,
                                                   ctypes.byref(typ), buf,
                                                   ctypes.byref(size)) == 0:
                            val = os.path.expandvars(buf.value).rstrip("\\/")
                            if val:
                                return Path(val)
                finally:
                    advapi.RegCloseKey(hkey)
        except Exception:
            pass
    return home_dir() / "Downloads"


def default_out_dir() -> Path:
    return windows_download_dir()


_LEGACY_OUT_DIRS = {"Z:\\太极营", "Z:/太极营"}


def effective_out_dir(cfg: dict | None = None) -> Path:
    """目录记忆规则：空 → 下载文件夹；旧脏值且不存在 → 回落；自定目录盘没挂 → 照记不偷改。"""
    cfg = cfg or {}
    raw = (cfg.get("out_dir") or "").strip()
    if not raw:
        return default_out_dir()
    if raw in _LEGACY_OUT_DIRS and not Path(raw).exists():
        return default_out_dir()
    return Path(raw)


# ── 凭据 ──────────────────────────────────────────────────────────────

def load_cookie() -> str:
    """XQD_COOKIE → QLD_COOKIE → ~/.xqd_tool/cookie.txt（单一入口，别到处找）。"""
    for key in ("XQD_COOKIE", "QLD_COOKIE"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    try:
        return cred_file().read_text(encoding="utf-8").strip()
    except Exception:
        return ""
