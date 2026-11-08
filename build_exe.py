# -*- coding: utf-8 -*-
"""PyInstaller 打包脚本：产出单文件 exe。

用法：
    python build_exe.py              # 正式打包
    python build_exe.py --dry-run    # 只打印命令，不执行

产物：dist/xqd-downloader-v<版本>.exe（版本取自 xqd_gui.APP_VERSION）

★ exe 文件名一律用 ASCII。GitHub Releases 会把中文附件名吞成
  ``default.exe``，而 96 MB 的附件一旦发布（immutable release）就改不了名，
  重传代价很高。窗口标题、界面文字仍是中文，见 xqd_gui.APP_TITLE。
"""

import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE_BASENAME = 'xqd-downloader'

# 需要一起打进去的自有模块
HIDDEN = [
    'xqd_auth',
    'xqd_creds',      # 凭据读取（env -> 私有文件），不含任何真实凭据
    'xqd_dedupe',
    'xqd_engine',
    'xqd_platform',
    'xqd_proc',       # 无控制台窗口地调子进程（防 Windows Terminal 闪窗）
]

EXCLUDE = [
    'matplotlib', 'numpy', 'pandas', 'scipy', 'tkinter', 'IPython',
    'jupyter', 'notebook', 'PyQt5', 'PyQt6', 'flask', 'django',
    'setuptools', 'pip', 'wheel',
]


def app_version():
    """从源码读 APP_VERSION；用正则而不用 import，避免打包前拉起 Qt。"""
    try:
        with open(os.path.join(ROOT, 'xqd_gui.py'), encoding='utf-8') as f:
            src = f.read()
        m = re.search(r"^APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", src, re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    return 'dev'


def exe_name():
    """纯 ASCII 产物名（不含扩展名），与 Release tag ``v<版本>`` 对齐。"""
    return '%s-v%s' % (EXE_BASENAME, app_version())


def _pyside6_root():
    """定位 PySide6 安装目录（打包时需要收集 Qt 的 DLL 与 plugins）。"""
    try:
        import PySide6
        return os.path.dirname(PySide6.__file__)
    except Exception:
        return None


def build_cmd():
    """构造 PyInstaller 命令。单独成函数，便于离线核对产物名与参数。"""
    if shutil.which('pyinstaller') is None:
        print('pyinstaller 不在 PATH，尝试用 -m 调用')
        base = [sys.executable, '-m', 'PyInstaller']
    else:
        base = ['pyinstaller']

    cmd = base + [
        '--onefile',
        '--windowed',              # 不弹控制台
        '--name', exe_name(),
        '--noconfirm',
        '--clean',
        '--distpath', os.path.join(ROOT, 'dist'),
        '--workpath', os.path.join(ROOT, 'build'),
        '--specpath', os.path.join(ROOT, 'build'),
    ]
    for m in HIDDEN:
        cmd += ['--hidden-import', m]
    for m in EXCLUDE:
        cmd += ['--exclude-module', m]

    # ── PySide6 的 DLL 与平台插件必须显式收集 ──
    # 只靠 PyInstaller's hook 会漏掉 Qt6Core.dll 等运行时依赖，
    # 表现为 exe 双击无窗口、日志报 "DLL load failed while importing QtCore"
    #
    # PySide6-Essentials 的目录布局：
    #   <site-packages>/PySide6/Qt6Core.dll ...   ← DLL 在顶层
    #   <site-packages>/PySide6/plugins/platforms/qwindows.dll
    #   <site-packages>/PySide6/plugins/styles/...
    ps = _pyside6_root()
    if ps and os.path.isdir(ps):
        # 顶层所有 DLL（Qt6*.dll）与 .json 配置
        dlls = [f for f in os.listdir(ps)
                if f.lower().endswith(('.dll', '.json'))]
        for f in dlls:
            cmd += ['--add-data',
                    '%s%s%s' % (os.path.join(ps, f), os.pathsep, '.')]

        # 平台插件（qwindows.dll 等）必须落在 plugins/ 下
        plugins_src = os.path.join(ps, 'plugins')
        if os.path.isdir(plugins_src):
            for entry in os.listdir(plugins_src):
                sub = os.path.join(plugins_src, entry)
                if os.path.isdir(sub):
                    cmd += ['--add-data',
                            '%s%s%s' % (sub, os.pathsep,
                                       os.path.join('plugins', entry))]
        print('收集 %d 个 Qt DLL + plugins/' % len(dlls))

    cmd.append(os.path.join(ROOT, 'xqd_gui.py'))
    return cmd


def main():
    name = exe_name()
    cmd = build_cmd()

    print('产物：dist/%s.exe' % name)
    print('执行：', ' '.join(cmd))
    if '--dry-run' in sys.argv[1:]:
        print('--dry-run：未执行打包')
        return 0

    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print('打包失败 rc=%s' % r.returncode)
        return r.returncode

    exe = os.path.join(ROOT, 'dist', name + '.exe')
    if os.path.isfile(exe):
        print('\n✅ 打包完成：%s（%.1f MB）'
              % (exe, os.path.getsize(exe) / 1048576.0))
    else:
        print('\n❌ 未找到产物')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
