# -*- coding: utf-8 -*-
"""无控制台窗口、且不带 Qt 环境污染地调用子进程。

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

第二个职责：环境隔离
--------------------
打包后的程序是 PySide6(Qt6)，运行时会往环境里注入
``QT_PLUGIN_PATH``（指向 Qt6 插件目录）等变量。子进程若原样继承，
MuMu 的 Qt5 程序就会加载错版本插件，弹出
「no Qt platform plugin could be initialized」。
本模块在**每次创建子进程时**净化这些变量（详见下方注释）。
"""

import os
import re
import subprocess
import sys

# ★ CREATE_NO_WINDOW = 0x08000000，让子进程不弹控制台窗口
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

_IS_WIN = sys.platform == 'win32'

# ── Qt 环境隔离（★ 根因修复：MuMu "no Qt platform plugin" 弹窗）────
# 本工具是 PySide6(Qt6) 程序。PyInstaller 打包后，它的 PySide6 运行时
# hook（hooks/rthooks/pyi_rth_pyside6.py）会**无条件**往进程环境里写：
#
#     QT_PLUGIN_PATH     = <_MEIPASS>\PySide6\plugins   ← Qt6 插件目录
#     QML2_IMPORT_PATH   = <_MEIPASS>\PySide6\qml
#     PATH               = <_MEIPASS>;<原来的 PATH>
#
# 子进程默认继承这些变量。而 MuMu 全家（MuMuManager / MuMuNxMain）是
# **Qt5** 程序：一旦某个子命令初始化 QGuiApplication，就会去
# QT_PLUGIN_PATH 找平台插件，加载到 Qt6 的 qwindows.dll，符号对不上 →
#
#   This application failed to start because no Qt platform plugin
#   could be initialized. Available platform plugins are: windows.
#
# 授权流程一次要调十几次 MuMuManager（is_running / launch / sh /
# close_all…），所以这个框会连着弹好几次。源码方式运行
# （python xqd_gui.py）不注入这些变量，因此只在打包 exe 上复现 ——
# 这也是「反复出现、时有时无」的原因。
#
# ★ 净化必须做在**子进程创建处**：MuMu 的 GUI 主程序是
#   `control launch` 拉起的**孙进程**，它继承的是 MuMuManager 的环境，
#   只改当前进程的环境变量来不及（而且会弄坏自己的 Qt6 界面）。
_QT_ENV_PREFIXES = ('QT_', 'QML')
_PYI_ENV_PREFIXES = ('_PYI_',)
_PYI_ENV_KEYS = ('_MEIPASS2',)
_MEI_DIR_RE = re.compile(r'_MEI\d{3,}', re.I)


def clean_env(base=None):
    """返回一份不含 Qt / PyInstaller 注入变量的子进程环境。

    只移除注入项，普通变量（PATH、TEMP、SYSTEMROOT…）原样保留；
    对 ffmpeg / tasklist 之类非 Qt 子进程完全无害。
    """
    env = dict(base if base is not None else os.environ)
    for key in list(env):
        up = key.upper()
        if (up.startswith(_QT_ENV_PREFIXES)
                or up.startswith(_PYI_ENV_PREFIXES)
                or up in _PYI_ENV_KEYS):
            env.pop(key, None)
    return env


def _mumu_dir(cmd):
    """命令若指向 MuMuManager.exe，返回它所在目录，否则返回 ''。"""
    try:
        if isinstance(cmd, (list, tuple)):
            exe = cmd[0] if cmd else ''
        else:
            exe = str(cmd).split(' ')[0].strip('"')
    except Exception:
        return ''
    if os.path.basename(str(exe)).lower() == 'mumumanager.exe':
        return os.path.dirname(os.path.abspath(exe))
    return ''


def _strip_pyi_paths(path):
    """从 PATH 里剔除 PyInstaller 临时目录与 PySide6 目录（只对 MuMu 用）。

    这些目录里全是 Qt6 DLL，留着可能让 MuMu 的 Qt5 进程加载错版本。
    ffmpeg 等其它子进程不剔 —— 打包版可能真需要 _MEIPASS 里的 DLL。
    """
    kept = []
    for part in (path or '').split(os.pathsep):
        if not part:
            continue
        if _MEI_DIR_RE.search(part):
            continue
        if os.path.basename(part.rstrip('\\/')).lower() == 'pyside6':
            continue
        kept.append(part)
    return os.pathsep.join(kept)


def _prepare_kwargs(cmd, kwargs):
    """给子进程补上 env / cwd（调用方显式传了 env 时完全尊重调用方）。"""
    kwargs = dict(kwargs)
    if kwargs.get('env') is not None:
        return kwargs
    env = clean_env()
    md = _mumu_dir(cmd)
    if md:
        # ★ 双重保险：不光清掉污染，还显式指向 MuMu 自带的 Qt5 插件目录。
        #   孙进程（MuMuNxMain.exe 等）继承这份环境，同样被纠正。
        plugins = os.path.join(md, 'plugins')
        platforms = os.path.join(plugins, 'platforms')
        if os.path.isdir(platforms):
            env['QT_PLUGIN_PATH'] = plugins
            env['QT_QPA_PLATFORM_PLUGIN_PATH'] = platforms
        env['PATH'] = _strip_pyi_paths(env.get('PATH', ''))
        if kwargs.get('cwd') is None:
            kwargs['cwd'] = md
    kwargs['env'] = env
    return kwargs


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


def _cmd_of(args, kwargs):
    return args[0] if args else kwargs.get('args')


def run(*args, **kwargs):
    """``subprocess.run`` 的无窗 + Qt 环境隔离版本。

    用法与 subprocess.run 完全一致，只是自动加上
    CREATE_NO_WINDOW / STARTF_USESHOWWINDOW，并净化继承的 Qt 环境变量。
    """
    kwargs = _prepare_kwargs(_cmd_of(args, kwargs), kwargs)
    kwargs.update(_no_window_kwargs())
    return subprocess.run(*args, **kwargs)


def check_output(*args, **kwargs):
    """``subprocess.check_output`` 的无窗 + Qt 环境隔离版本。"""
    kwargs = _prepare_kwargs(_cmd_of(args, kwargs), kwargs)
    kwargs.update(_no_window_kwargs())
    return subprocess.check_output(*args, **kwargs)


def popen(*args, **kwargs):
    """``subprocess.Popen`` 的无窗 + Qt 环境隔离版本。"""
    kwargs = _prepare_kwargs(_cmd_of(args, kwargs), kwargs)
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
