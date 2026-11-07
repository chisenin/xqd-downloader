# -*- coding: utf-8 -*-
"""无控制台窗口地调用子进程。

为什么需要这个
--------------
打包后的 exe 用的是 ``--windowed``（自己不带控制台窗口），
但它要调用的这些程序**全是控制台子系统**：

* ``MuMuManager.exe`` —— 网易 MuMu 的命令行管理器（21MB 控制台程序）
* ``tasklist``       —— Windows 自带控制台程序
* ``ffmpeg`` / ``ffprobe``

Windows 的规则是：**控制台程序从一个没有控制台的进程启动时，
会自动新建一个控制台窗口**。这个窗口会在子进程退出瞬间销毁，
于是用户看到的就是「一闪而逝的黑框」—— 启动流程里
``is_running`` / ``main_running`` / ``launch_player`` / 读 Cookie
各调一次，正好就是「几次」。

解决办法是给子进程加 ``CREATE_NO_WINDOW`` 创建标志，
让它**不分配控制台**，输出照样走管道接回来。

★ 只在 Windows 上生效；其它平台原样调用（``creationflags=0``）。
"""

import os
import subprocess
import sys

# ★ CREATE_NO_WINDOW = 0x08000000，让子进程不弹控制台窗口
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

_IS_WIN = sys.platform == 'win32'


def _no_window_kwargs():
    """subprocess 的额外关键字参数（隐藏控制台窗口）。"""
    if not _IS_WIN:
        return {}
    # STARTUPINFO + SW_HIDE 是第二道保险：
    # 某些程序（如 tasklist 的某些版本）会自己改回可见。
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0            # SW_HIDE
    return {'creationflags': _NO_WINDOW, 'startupinfo': si}


def run(*args, **kwargs):
    """``subprocess.run`` 的无窗版本。

    用法与 subprocess.run 完全一致，只是自动加上
    CREATE_NO_WINDOW / STARTF_USESHOWWINDOW。
    """
    kwargs.update(_no_window_kwargs())
    return subprocess.run(*args, **kwargs)


def check_output(*args, **kwargs):
    """``subprocess.check_output`` 的无窗版本。"""
    kwargs.update(_no_window_kwargs())
    return subprocess.check_output(*args, **kwargs)


def popen(*args, **kwargs):
    """``subprocess.Popen`` 的无窗版本。"""
    kwargs.update(_no_window_kwargs())
    return subprocess.Popen(*args, **kwargs)


def is_console_app(path):
    """判断一个 exe 是否为控制台子系统程序（仅调试用）。

    读 PE 头的 Subsystem 字段：2 = GUI，3 = 控制台。
    """
    try:
        with open(path, 'rb') as f:
            head = f.read(1024)
        if head[:2] != b'MZ':
            return False
        pe_off = int.from_bytes(head[0x3c:0x40], 'little')
        if head[pe_off:pe_off + 4] != b'PE\0\0':
            return False
        # OptionalHeader 偏移 0x44 处是 Subsystem（16 位）
        sub = int.from_bytes(head[pe_off + 0x5c:pe_off + 0x5e], 'little')
        return sub == 3
    except Exception:
        return False
