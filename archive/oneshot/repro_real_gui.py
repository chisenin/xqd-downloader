# -*- coding: utf-8 -*-
"""真实数据复现：选中一节课开始下载后，课程表里其它行被误标成「已存在」。

用真实 API 拉课表 + 真实 Z 盘目录 + 真实 GUI 代码路径。
下载用假实现（不联网），只观察行状态写入。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

import xqd_gui
import xqd_platform
import xqd_engine

# ★ 凭据不在源码里 —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import xqd_creds            # noqa: E402

COOKIE = xqd_creds.load_cookie()

OUT = 'Z:/太极营'
CAMP = os.environ.get('XQDCAMP', '五行养生音乐')


def snap(win, tag):
    print('---- %s ----' % tag)
    out = {}
    for r in range(win.tbl_lessons.rowCount()):
        it = win.tbl_lessons.item(r, 1)
        cb = win.tbl_lessons.item(r, 0)
        txt = it.text() if it else ''
        chk = cb.checkState() if cb else None
        out[r] = (txt, chk)
        print('  row%-2d chk=%-22s %s' % (r, chk, txt))
    return out


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    win = xqd_gui.MainWindow()
    win.ed_out.setText(OUT)
    win.out_dir = OUT
    win.cookie = COOKIE
    win.platform.cookie = COOKIE
    win.auto_check_auth = lambda: None

    # 假下载：写一个真的小文件，但**故意慢**，让后台扫描有机会插进来
    def fake_download(resolve_url, out_path, quality='max', workers=12,
                     tmp_root=None, on_progress=None, stop_flag=None,
                     expect_duration=0, control=None, on_phase=None):
        time.sleep(1.5)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(b'x' * 30000)
        if on_progress:
            on_progress(100, 100, 100.0, 100.0)
        return True, '假下载完成', out_path

    xqd_engine.download_lesson = fake_download

    camps = win.platform.list_camps('正式营')
    camp = [c for c in camps if c.name == CAMP][0]
    win.camps = camps
    win.current_camp = camp
    win.load_lessons()
    app.processEvents()
    print('营：%s  共 %d 节' % (camp.name, len(win.lessons)))

    # 等扫描完成
    t0 = time.time()
    while win.scan_worker and win.scan_worker.isRunning() \
            and time.time() - t0 < 60:
        app.processEvents()
        time.sleep(0.2)
    app.processEvents()
    before = snap(win, '扫描完成后（下载前）')

    # 勾选第 1 节
    win.tbl_lessons.item(0, 0).setCheckState(Qt.Checked)
    app.processEvents()

    # ★ 关键：先触发「重新扫描」（模拟用户点了重新扫描按钮，或切营回来）
    print('\n>>> 触发 rescan_existing()')
    win.rescan_existing()
    # 立刻开始下载（不等扫描）
    win._start_downloads([(0, win.lessons[0])])

    for i in range(8):
        time.sleep(0.4)
        app.processEvents()
        snap(win, '下载中 t=%.1f' % ((i + 1) * 0.4))

    time.sleep(2.0)
    app.processEvents()
    after = snap(win, '下载后')

    print('\n=== 变化 ===')
    for i in sorted(before):
        if before[i][0] != after[i][0]:
            print('row %d: %s  ->  %s' % (i, before[i][0], after[i][0]))


if __name__ == '__main__':
    main()
