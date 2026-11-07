# -*- coding: utf-8 -*-
"""启动闪窗诊断：监控真实 exe 启动期间出现的所有新窗口。

用法：
    python _lel/api/spy_windows.py <秒数> [要启动的命令...]

会打印期间出现的**新窗口**（类名 / 标题 / 进程名 / 是否可见），
按出现顺序排列 —— 用来定位「一闪而逝的窗口」到底是什么。
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_process_names = {}


def _proc_name(pid):
    if pid in _process_names:
        return _process_names[pid]
    try:
        h = kernel32.OpenProcess(0x1000, False, pid)
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if h and kernel32.QueryFullProcessImageNameW(h, 0, buf,
                                                    ctypes.byref(size)):
            name = buf.value.rsplit('\\', 1)[-1]
        else:
            name = '?'
        kernel32.CloseHandle(h)
    except Exception:
        name = '?'
    _process_names[pid] = name
    return name


def snapshot():
    """当前所有顶层窗口：(类名, 标题, 进程名, 可见)"""
    out = []

    def cb(hwnd, lp):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        t = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, t, 512)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((buf.value, t.value, _proc_name(pid.value),
                    bool(user32.IsWindowVisible(hwnd))))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    cmd = sys.argv[2:] if len(sys.argv) > 2 else None

    before = {w[0] for w in snapshot()}
    seen = []
    order = []
    t_end = time.time() + dur
    child = None
    if cmd:
        child = subprocess.Popen(cmd)

    while time.time() < t_end:
        for w in snapshot():
            key = (w[0], w[1], w[2])
            if key not in seen:
                seen.append(key)
                order.append((time.time(), w))
        time.sleep(0.02)

    print('=== 启动期间新出现的窗口 ===')
    t0 = order[0][0] if order else 0
    for ts, w in order:
        if w[0] in before:
            continue
        print('%6.2fs  %-28s pid=%-14s 可见=%-5s  %s'
              % (ts - t0, w[0], w[2], w[3], w[1][:60]))

    print('\n=== 按进程统计 ===')
    stat = {}
    for ts, w in order:
        if w[0] in before:
            continue
        stat.setdefault(w[2], []).append(w[0])
    for p, cls in sorted(stat.items()):
        print('  %-30s %s' % (p, sorted(set(cls))))

    if child:
        try:
            child.terminate()
        except Exception:
            pass


if __name__ == '__main__':
    main()
