# -*- coding: utf-8 -*-
"""最小化复现：GUI 里下载一节课。

用真实的 DownloadWorker + 真实的 MainWindow，但只下一个营的一节。
目的：定位 GUI 路径与独立调用路径的差异（独立调用能下出 1GB 文件，
GUI 却什么都没有且进程直接消失）。
"""
import faulthandler
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

try:
    faulthandler.enable(file=sys.stderr, all_threads=True)
except Exception:
    pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

import xqd_gui

COOKIE = ('rsessionId=<RSESSION_ID>'
          '<RSESSION_ID_TAIL>; '
          'userId=<USER_ID>; cUserId=<C_USER_ID>; '
          'uid=<UID>; '
          'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')

CAMP = sys.argv[1] if len(sys.argv) > 1 else '太极中阶复训营'
IDX = int(sys.argv[2]) if len(sys.argv) > 2 else 1
OUT = 'Z:/太极营'


def log(m):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    xqd_gui.MainWindow.auto_check_auth = lambda self: None

    win = xqd_gui.MainWindow()
    win.out_dir = OUT
    win.ed_out.setText(OUT)
    win.cookie = COOKIE
    win.platform.cookie = COOKIE
    win.show()

    _glog = win.log

    def glog(t):
        print('    | %s' % t, flush=True)
        _glog(t)
    win.log = glog

    st = {'phase': 'a'}

    def s_a():
        win.load_camps()
        for i, c in enumerate(win.camps):
            if c.name == CAMP:
                win.lst_camps.setCurrentRow(i)
        log('课表 %d 节' % len(win.lessons))
        st['phase'] = 'b'

    def s_b():
        le = win.lessons[IDX]
        log('目标课：%s  时长 %s' % (le.title, le.duration))
        # 直接用 GUI 的 _start_downloads（与点「下载选中」同一条路径）
        win._start_downloads([(IDX, le)])
        log('已调用 _start_downloads，running=%d queued=%d'
            % (len(win.running_workers), len(win.pending_queue)))
        st['phase'] = 'c'

    def s_c():
        if win.running_workers or win.pending_queue:
            return False
        log('全部结束')
        st['phase'] = 'z'
        return True

    def s_z():
        app.quit()
        return True

    steps = {'a': s_a, 'b': s_b, 'c': s_c, 'z': s_z}
    timer = QTimer()
    timer.timeout.connect(lambda: steps.get(st['phase'], lambda: False)())
    timer.start(1000)

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
