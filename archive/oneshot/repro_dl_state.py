# -*- coding: utf-8 -*-
"""复现：开始下载后，课程表里多行被误标成「已存在/已完成」。

用假平台 + 假下载（不联网），只观察 GUI 的行状态写入。
"""
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt

import xqd_gui
import xqd_platform
import xqd_engine

OUT = os.path.join(tempfile.gettempdir(), 'xqd_repro_dl')


def fake_lesson(i):
    le = xqd_platform.Lesson(
        index=i, title='第%d讲 测试课程' % (i + 1), when='07.0%d 06:00' % (i + 1),
        duration=600, ltype='VIDEO', topic_id='t%d' % i, room_id='r%d' % i,
        camp='测试营')
    le.when_date = '2026.07.%02d' % (i + 1)
    return le


class FakePlatform(object):
    platform_id = 'fake'
    display_name = '假平台'
    camp_kinds = ('正式营',)

    def __init__(self):
        self.lessons = [fake_lesson(i) for i in range(5)]
        self.camp = xqd_platform.Camp('测试营', 'c1', '正式营', 5, '5节')

    def list_camps(self, kind='正式营'):
        return [self.camp]

    def camp_catalog(self, camp):
        return self.lessons

    def resolve(self, camp, lesson):
        return 'http://example.com/x.m3u8'


def snapshot(win, tag):
    rows = []
    for r in range(win.tbl_lessons.rowCount()):
        it = win.tbl_lessons.item(r, 1)
        cb = win.tbl_lessons.item(r, 0)
        rows.append((r,
                     (it.text() if it else ''),
                     (cb.checkState() if cb else None)))
    print('---- %s ----' % tag)
    for r, txt, ck in rows:
        print('  row%-2d chk=%-2s %s' % (r, ck, txt))
    return rows


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    win = xqd_gui.MainWindow()
    win.ed_out.setText(OUT)
    win.out_dir = OUT
    win.cookie = 'fake=1'
    win.platform = FakePlatform()
    win.auto_check_auth = lambda: None

    # 假下载：慢一点，方便观察中间状态
    def fake_download(resolve_url, out_path, quality='max', workers=12,
                     tmp_root=None, on_progress=None, stop_flag=None,
                     expect_duration=0, control=None, on_phase=None):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        time.sleep(2.0)
        with open(out_path, 'wb') as f:
            f.write(b'x' * 20000)
        if on_progress:
            on_progress(100, 100, 100.0, 100.0)
        return True, '假下载完成', out_path

    real_dl = xqd_engine.download_lesson
    xqd_engine.download_lesson = fake_download

    win.current_camp = win.platform.camp
    win.camps = [win.platform.camp]
    win.load_lessons()
    app.processEvents()

    before = snapshot(win, '下载前')

    # 勾选第 1 节
    win.tbl_lessons.item(0, 0).setCheckState(Qt.Checked)
    app.processEvents()

    win._start_downloads([(0, win.lessons[0])])

    # 观察 3 秒内的行状态变化
    for i in range(6):
        time.sleep(0.5)
        app.processEvents()
        snapshot(win, '下载中 t=%.1f' % ((i + 1) * 0.5))

    time.sleep(2.0)
    app.processEvents()
    after = snapshot(win, '下载后')

    xqd_engine.download_lesson = real_dl
    print('\n=== 结论 ===')
    for i, (b, a) in enumerate(zip(before, after)):
        if b[1] != a[1]:
            print('row %d 变化：%s  ->  %s' % (i, b[1], a[1]))


if __name__ == '__main__':
    main()
