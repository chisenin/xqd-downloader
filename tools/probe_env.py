#!/usr/bin/env python3
"""环境探测脚本 —— 相当于 C# 版的 `xqd-downloader --check`。

用法（在仓库根目录）：
    python tools/probe_env.py
    python tools/probe_env.py --json     给别的脚本吃

它做的事：列出配置目录 / 下载目录 / ffmpeg / ffprobe / MuMu / adb / 在线设备，
缺什么直接告诉你「怎么办」，不猜、不自动下载。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from xqd import __version__                      # noqa: E402
from xqd import config                           # noqa: E402
from xqd.probe import find_adb, report           # noqa: E402

ICON = {True: "[OK]", False: "[--]"}


def main() -> int:
    ap = argparse.ArgumentParser(description="兴趣岛下载器 · 环境探测")
    ap.add_argument("--json", action="store_true", help="输出 JSON（给脚本/CI 用）")
    args = ap.parse_args()

    cfg = config.load_config()
    out_dir = config.effective_out_dir(cfg)
    items = report()

    if args.json:
        print(json.dumps({
            "version": __version__,
            "tool_dir": str(config.tool_dir()),
            "out_dir": str(out_dir),
            "deps": items,
        }, ensure_ascii=False, indent=2))
        return 0 if all(i["ok"] for i in items if i["required"]) else 1

    print(f"xqd-downloader {__version__}  (Python 核心库)")
    print(f"配置目录：{config.tool_dir()}")
    print(f"下载目录：{out_dir}   {'（配置文件里记的）' if cfg.get('out_dir') else '（系统下载文件夹）'}")
    print(f"凭据文件：{config.cred_file()}   "
          f"{'已存在' if config.cred_file().exists() else '未找到'}")

    print("\n依赖：")
    for it in items:
        mark = "必需" if it["required"] else "可选"
        print(f"  {ICON[it['ok']]} {it['name']:<22} {mark}")
        if it["ok"]:
            print(f"        → {it['path']}")
        else:
            print(f"        {it['hint']}")

    missing_required = [i["name"] for i in items if i["required"] and not i["ok"]]
    if missing_required:
        print("\n缺必需依赖：" + "、".join(missing_required))
        print("  · 图形版：打开程序 → 顶栏「环境检查」→ 一键安装 ffmpeg")
        print(f"  · 手动：把 ffmpeg.exe/ffprobe.exe 放进 {config.ffmpeg_tool_dir()}")
        print("          或设环境变量 XQD_FFMPEG_DIR 指向它们的目录")
        return 1

    adb = items[3]["path"] if len(items) > 3 else ""
    if adb:
        print(f"\nadb：{adb}")
    print("\n全部必需依赖就绪。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
