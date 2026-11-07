# -*- coding: utf-8 -*-
"""★ GUI 层的真实跨会话验证（真网络 + 真 Cookie）。

模拟用户的完整动作：
  1. 打开工具 → 授权 → 加载营列表 → 选营 → 加载课表
  2. 勾一节课 → 开始下载（**中途失败**，模拟断网）
  3. 关闭工具（closeEvent 会落盘历史）
  4. **重新打开工具** → 验证「下载管理」表里恢复了上次的记录

这是需求三在**界面层**的最终验证。

用法：python test_gui_history_real.py
"""
import os
import tempfile
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_engine
import xqd_history
import xqd_platform

PASS = []
FAIL = []

# ★ 不要在这里硬编码 Cookie —— 会过期，而且脱敏时容易把内容改坏。
#   统一走 xqd_creds（env -> 私有文件 -> 抓包原件），见 xqd_creds.py。
COOKIE = ''


def load_cookie():
    """取真 Cookie —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）。"""
    global COOKIE
    import xqd_creds
    try:
        COOKIE = xqd_creds.load_cookie()
    except Exception as e:
        print('  读 Cookie 失败：%s' % e)
        return False
    return bool(COOKIE)

# ★ 历史文件放到独立位置，别污染用户真实的 ~/.xqd_tool/history.json
TEST_HOME = os.path.join(ROOT, 'state', 'gui_hist_home')
os.makedirs(TEST_HOME, exist_ok=True)
HIST_FILE = os.path.join(TEST_HOME, 'history.json')
if os.path.exists(HIST_FILE):
    os.remove(HIST_FILE)


def ok(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('OK  ' if cond else 'FAIL', name,
                       ('  -> %s' % (extra,)) if extra else ''))


def patch_paths():
    """把历史文件路径指到测试目录。

    ★ xqd_gui 一律通过 xqd_history.xxx() 访问历史，
      所以只需要改 xqd_history 的常量。
    """
    xqd_history.HISTORY_FILE = HIST_FILE
    xqd_history.PARTS_DIR = os.path.join(TEST_HOME, 'parts')


def main():
    if not load_cookie():
        print('★ 拿不到真 Cookie（xqd_creds / ~/.xqd_tool/cookie.txt），跳过')
        return 1
    patch_paths()
    app = QApplication(sys.argv)

    # ══ 场景 1：第一次打开工具 ═══════════════════════════════
    print('\n──── 场景 1：第一次打开工具 ────')
    win = xqd_gui.MainWindow()
    win.ed_out.setText(os.path.join(ROOT, 'state', 'gui_hist_out'))
    win.out_dir = win.ed_out.text()
    win.auto_check_auth = lambda: None
    app.processEvents()

    plat = xqd_platform.create_platform('qianliao', cookie=COOKIE)
    win.platform = plat
    win.cookie = COOKIE
    camps = plat.list_camps()
    ok('营列表加载成功', len(camps) > 0, '%d 个营' % len(camps))
    win.camps = camps
    win.current_camp = camps[0]

    win.load_lessons()
    app.processEvents()
    n_lessons = len(win.lessons)
    ok('课表加载成功', n_lessons > 0, '%d 节' % n_lessons)

    hdr = win.tbl_lessons.horizontalHeaderItem(1)
    ok('表头带计数', hdr is not None and '(' in hdr.text(),
       hdr.text() if hdr else '')
    hdr2 = win.tbl_lessons.horizontalHeaderItem(2)
    ok('第 3 列是「标题后缀」', hdr2 is not None and '标题后缀' in hdr2.text(),
       hdr2.text() if hdr2 else '')

    # ══ 场景 2：开始下载（中途失败）════════════════════════════
    print('\n──── 场景 2：下载中途失败 ────')
    le = win.lessons[0]
    out_path = os.path.join(win.out_dir, win._camp_folder(win.current_camp),
                            xqd_history.make_record and
                            ('%02d.%s.mp4' % (1, le.title)))
    out_path = os.path.join(os.path.dirname(out_path),
                            out_path.replace(':', '_'))

    real_get = xqd_engine.http_get
    allow = {'n': 0}

    def limited_get(url, timeout=30):
        if '.ts' in url and '?' in url:
            if allow['n'] >= 8:
                return 0, b''
            allow['n'] += 1
        return real_get(url, timeout=timeout)

    xqd_engine.http_get = limited_get
    try:
        win._start_downloads([(0, le)])
        deadline = time.time() + 240
        while time.time() < deadline:
            app.processEvents()
            time.sleep(0.1)
            st = win.tbl_tasks.item(0, 2).text() if win.tbl_tasks.rowCount() else ''
            if st in ('失败', '已完成'):
                break
    finally:
        xqd_engine.http_get = real_get

    st = win.tbl_tasks.item(0, 2).text() if win.tbl_tasks.rowCount() else ''
    ok('任务行状态为「失败」', st == '失败', st)
    ok('下载管理表有 1 行', win.tbl_tasks.rowCount() == 1,
       str(win.tbl_tasks.rowCount()))

    # 历史应已落盘
    ok('历史文件已生成', os.path.isfile(HIST_FILE))
    hist = xqd_history.load_history(HIST_FILE)
    ok('历史里有 1 条记录', len(hist) == 1, str(len(hist)))

    # ══ 场景 3：关闭工具 ═══════════════════════════════════════
    print('\n──── 场景 3：关闭工具 ────')
    win.close()
    app.processEvents()
    time.sleep(0.5)
    ok('关闭后历史仍在', os.path.isfile(HIST_FILE))

    # ══ 场景 4：重新打开工具 ═══════════════════════════════════
    print('\n──── 场景 4：重新打开工具 ────')
    win2 = xqd_gui.MainWindow()
    win2.ed_out.setText(os.path.join(ROOT, 'state', 'gui_hist_out'))
    win2.out_dir = win2.ed_out.text()
    win2.auto_check_auth = lambda: None
    app.processEvents()

    n = win2.tbl_tasks.rowCount()
    ok('重开后恢复了下载列表', n == 1, '%d 行' % n)
    if n:
        st2 = win2.tbl_tasks.item(0, 2).text()
        ok('恢复的状态是「失败」', st2 == '失败', st2)
        p2 = win2.tbl_tasks.item(0, 1).data(Qt.UserRole)
        ok('恢复的路径非空', bool(p2), str(p2))
        cb = win2.tbl_tasks.item(0, 0)
        ok('恢复的行未勾选（不会自动重下）',
           cb.checkState() == Qt.Unchecked)

    # 分片缓存还在 → 应该是「可续传」而不是从零开始
    seg = xqd_history.parts_dir_for(p2) if n else None
    cached, cnt, _ = xqd_history.parts_progress(seg) if seg else (0, 0, 0)
    print('  · 恢复后可见缓存分片：%d 个 / %.1f MB'
          % (cnt, cached / 1048576.0))
    ok('分片缓存仍在（可续传）', cnt > 0, '%d 个' % cnt)

    win2.close()
    app.processEvents()

    print('\n========================================================')
    print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：', FAIL)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
