# -*- coding: utf-8 -*-
"""复现：ScanWorker 线程仍在运行时被 GC 析构 → Qt abort。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

import xqd_gui
import xqd_platform as P

COOKIE = os.environ.get('XQD_COOKIE', '')
OUT = os.environ.get('XQD_OUT', 'Z:/太极营')


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)
    xqd_gui.MainWindow.auto_check_auth = lambda self: None

    win = xqd_gui.MainWindow()
    win.show()
    win.out_dir = OUT
    win.ed_out.setText(OUT)
    win.cookie = COOKIE
    win.platform.cookie = COOKIE

    state = {'n': 0}

    def step():
        state['n'] += 1
        n = state['n']
        print('--- 第 %d 次 load_camps ---' % n, flush=True)
        win.cmb_kind.setCurrentText('正式营')
        win.load_camps()
        # 立刻再切一次（模拟驱动脚本切营）
        win.cmb_kind.setCurrentText('体验营')
        win.load_camps()
        print('    上一次 scan_worker 运行中? %s'
              % (win.scan_worker.isRunning()
                 if win.scan_worker else None), flush=True)
        if n >= 5:
            print('5 轮完成，没有崩溃', flush=True)
            app.quit()

    t = QTimer()
    t.timeout.connect(step)
    t.start(300)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
