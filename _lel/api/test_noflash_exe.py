# -*- coding: utf-8 -*-
"""启动闪窗回归测试：真实 exe 启动期间**不应出现可见的宿主窗口**。

背景
----
Windows 11 的默认控制台宿主是 **Windows Terminal**。
打包后的 exe 是 ``--windowed``（自身无控制台），它要启动
``MuMuManager.exe`` / ``tasklist`` / ``ffprobe`` 这些**控制台子系统**程序
—— Windows 会为此拉起 Terminal 来托管那个控制台，
Terminal 窗口一闪即逝（用户看到的「一闪而逝的窗口」）。

实测（修复前）：
    3.54s  CASCADIA_HOSTING_WINDOW_CLASS  WindowsTerminal.exe  可见=True
           标题 = D:\\...\\MuMuManager.exe
    5.36s  CASCADIA_HOSTING_WINDOW_CLASS  WindowsTerminal.exe  可见=True
           标题 = ...\\ffmpeg-...bin\\ffprobe.exe

修复：所有子进程调用加 ``CREATE_NO_WINDOW``（见 ``xqd_proc.py``）。

检测方法
--------
用 ctypes ``EnumWindows`` 轮询启动期间出现的**可见**窗口，
断言：**不出现** CASCADIA_HOSTING_WINDOW_CLASS / PseudoConsoleWindow /
ConsoleWindowClass 这三类「控制台宿主」窗口。

用法：
    python _lel/api/test_noflash_exe.py [exe路径]
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

PASS = []
FAIL = []

# ★ 这些是「控制台宿主」窗口 —— 出现即代表闪窗
HOST_CLASSES = {
    'CASCADIA_HOSTING_WINDOW_CLASS',   # Windows Terminal
    'ConsoleWindowClass',               # 传统控制台
    'PseudoConsoleWindow',              # ConPTY 伪控制台
}


def ok(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('OK  ' if cond else 'FAIL', name,
                       ('  -> %s' % (extra,)) if extra else ''))


def _proc_name(pid):
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
    return name


def visible_host_windows():
    """当前所有**可见**的控制台宿主窗口。"""
    found = []

    def cb(hwnd, lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value in HOST_CLASSES:
            t = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, t, 512)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((buf.value, _proc_name(pid.value), t.value))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        root, 'dist', '兴趣岛视频下载器.exe')
    if not os.path.isfile(exe):
        print('找不到 exe：%s' % exe)
        return 1

    print('监控目标：%s' % exe)
    seen = []
    proc = subprocess.Popen([exe])

    t_end = time.time() + 32
    while time.time() < t_end:
        for w in visible_host_windows():
            if w not in seen:
                seen.append(w)
                print('  检出宿主窗口：%s / %s / %s' % w)
        time.sleep(0.02)

    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        pass

    print('\n=== 结论 ===')
    if seen:
        for cls, p, title in seen:
            print('  %s  pid=%s  %s' % (cls, p, title[:70]))
    else:
        print('  启动期间未出现任何可见的控制台宿主窗口')

    ok('启动期间无可见的控制台宿主窗口（不闪窗）',
       not seen, '%d 个：%s' % (len(seen),
                                [(x[0], x[1]) for x in seen[:3]]))

    print('\n========================================================')
    print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：', FAIL)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
