# -*- coding: utf-8 -*-
"""闪窗机制测试：``xqd_proc`` 的封装是否真的阻止了控制台窗口。

★ 为什么父进程要用 pythonw.exe
------------------------------
Windows 的规则是：**控制台程序从「已有控制台」的父进程启动时，
直接继承父进程的控制台，不会新建窗口**；
只有父进程**没有控制台**时，才会新建一个控制台窗口。

所以：
* 从 bash / cmd 里的 python.exe 启动子进程 → 继承已有控制台 → 测不出来
* 从 pythonw.exe（无控制台）启动 → 才会新建 → 这才是真实场景
  （打包后的 GUI exe 就是 ``--windowed``，自己没有控制台）

本测试用 **pythonw.exe 作为父进程**，靶子用 **cmd.exe**（纯控制台程序），
复现「无控制台父 → 控制台子」这个真实组合。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

PASS = []
FAIL = []


def ok(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('OK  ' if cond else 'FAIL', name,
                       ('  -> %s' % (extra,)) if extra else ''))


# 被测子脚本（由 pythonw 执行）：监视控制台窗口 → 起子进程 → 写结果
CHILD_SRC = r'''
# -*- coding: utf-8 -*-
import os, sys, time, threading, subprocess, ctypes
from ctypes import wintypes

ROOT, RESULT, MODE = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, ROOT)

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def consoles():
    found = []

    def cb(hwnd, lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value in ('ConsoleWindowClass', 'CASCADIA_HOSTING_WINDOW_CLASS',
                         'PseudoConsoleWindow'):
            t = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, t, 512)
            found.append(buf.value + '|' + (t.value or ''))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


seen = set()
stop = [False]


def watch():
    while not stop[0]:
        try:
            seen.update(consoles())
        except Exception:
            pass
        time.sleep(0.003)


t = threading.Thread(target=watch)
t.daemon = True
t.start()
time.sleep(0.2)

# ★ 靶子 = 纯控制台程序（cmd.exe），父进程无控制台 → 会新建窗口
CMD = [r'C:\Windows\System32\cmd.exe', '/c', 'ping -n 4 127.0.0.1 >nul']
if MODE == 'raw':
    subprocess.run(CMD, capture_output=True, timeout=30)
else:
    import xqd_proc
    xqd_proc.run(CMD, capture_output=True, timeout=30)

time.sleep(0.3)
stop[0] = True
with open(RESULT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(sorted(seen)))
'''


def run_mode(pythonw, child, root, mode):
    here = os.path.dirname(child)
    res_file = os.path.join(here, '_noflash_res_%s.txt' % mode)
    if os.path.exists(res_file):
        os.remove(res_file)
    subprocess.run([pythonw, child, root, res_file, mode], timeout=120)
    for _ in range(100):
        if os.path.exists(res_file):
            break
        time.sleep(0.1)
    try:
        with open(res_file, encoding='utf-8') as f:
            txt = f.read().strip()
    except Exception:
        txt = ''
    if os.path.exists(res_file):
        os.remove(res_file)
    return [x for x in txt.splitlines() if x.strip()]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    child = os.path.join(here, '_noflash_child.py')
    with open(child, 'w', encoding='utf-8') as f:
        f.write(CHILD_SRC)

    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if not os.path.isfile(pythonw):
        print('找不到 pythonw.exe（需要 Windows 的无控制台 Python），跳过')
        return 0

    raw = run_mode(pythonw, child, root, 'raw')
    proc = run_mode(pythonw, child, root, 'proc')

    if os.path.exists(child):
        os.remove(child)

    print('裸 subprocess（对照）  宿主窗口 %d 个：%s' % (len(raw), raw[:3]))
    print('xqd_proc（修复后）    宿主窗口 %d 个：%s' % (len(proc), proc[:3]))

    ok('对照组：无控制台父进程用裸 subprocess 确实会闪',
       len(raw) > 0, '%d 个' % len(raw))
    ok('修复后：xqd_proc.run 不闪', len(proc) == 0, '%d 个' % len(proc))

    # ── 输出与返回码不受影响 ──────────────────────────────
    import xqd_proc
    r = xqd_proc.run([sys.executable, '-c', 'print("hello-from-child")'],
                     capture_output=True, timeout=30)
    ok('输出照样接得到', b'hello-from-child' in r.stdout, r.stdout[:50])
    ok('returncode 正确', r.returncode == 0, r.returncode)

    r2 = xqd_proc.check_output(
        [sys.executable, '-c', 'import sys; sys.stdout.write("out")'],
        stderr=subprocess.DEVNULL, timeout=30)
    ok('check_output 照样接得到', b'out' in r2, r2[:50])

    # ── 真实调 MuMuManager / tasklist ─────────────────────
    try:
        import xqd_auth
        mgr = xqd_auth.find_mumu_manager()
        ok('找到 MuMuManager', True, os.path.basename(mgr))
        info = xqd_auth.player_info(mgr)
        ok('MuMuManager info 能正常返回', isinstance(info, dict),
           list(info)[:3])
        ok('tasklist 查询正常', xqd_auth.main_running() in (True, False))
    except Exception as e:
        ok('找到 MuMuManager', False, str(e))

    print('\n========================================================')
    print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：', FAIL)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
