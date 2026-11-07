# -*- coding: utf-8 -*-
"""复现：切营时旧的 ScanWorker 还在跑，它的结果按**旧课表下标**回传，
却被用来标记**新营**的行 —— 导致新营里「未完成」的课被误标成
「已存在」（勾选被取消，看起来像“自动变成已下载”）。
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
from PySide6.QtCore import Qt

import xqd_gui
import xqd_platform
import xqd_dedupe

OUT = os.path.join(tempfile.gettempdir(), 'xqd_repro_scan')


def mk_lessons(camp_name, n, tag):
    out = []
    for i in range(n):
        le = xqd_platform.Lesson(
            index=i, title='%s第%d讲' % (tag, i + 1), when='07.01 06:00',
            duration=600, ltype='VIDEO', topic_id='t', room_id='r',
            camp=camp_name)
        le.when_date = '2026.07.01'
        out.append(le)
    return out


class SlowChecker(xqd_dedupe.ExistingChecker):
    """每个文件查询慢 1 秒，模拟 SMB 盘上 ffprobe 的真实耗时。"""

    def check_group(self, folder, stem, expect_duration=0, alt_folders=None):
        time.sleep(0.35)
        # 假装前 3 个 stem 都有「已存在」的成品
        return {'status': 'ok' if stem.endswith('1') or stem.endswith('2')
                else 'missing',
                'files': [], 'path': 'fake', 'size': 12345678,
                'duration': 600.0, 'reason': 'fake'}


class FakePlatform(object):
    platform_id = 'fake'
    display_name = '假平台'
    camp_kinds = ('正式营',)

    def __init__(self):
        self.campA = xqd_platform.Camp('营A', 'a', '正式营', 6, '6节')
        self.campB = xqd_platform.Camp('营B', 'b', '正式营', 6, '6节')
        self.lessonsA = mk_lessons('营A', 6, 'A')
        self.lessonsB = mk_lessons('营B', 6, 'B')

    def list_camps(self, kind='正式营'):
        return [self.campA, self.campB]

    def camp_catalog(self, camp):
        return self.lessonsA if camp.name == '营A' else self.lessonsB

    def resolve(self, camp, lesson):
        return 'http://example.com/x.m3u8'


def snap(win, tag):
    print('---- %s ----' % tag)
    for r in range(win.tbl_lessons.rowCount()):
        it = win.tbl_lessons.item(r, 1)
        cb = win.tbl_lessons.item(r, 0)
        print('  row%-2d chk=%-22s %s'
              % (r, cb.checkState() if cb else None,
                 it.text() if it else ''))


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
    win.checker = SlowChecker(OUT)

    # 1) 加载营 A —— 扫描很慢
    win.current_camp = win.platform.campA
    win.camps = [win.platform.campA, win.platform.campB]
    win.load_lessons()
    print('营A 扫描线程在跑:', win.scan_worker.isRunning())

    # 2) 立刻切到营 B —— 旧扫描还没结束
    time.sleep(0.4)
    win.current_camp = win.platform.campB
    win.load_lessons()
    print('切到营B 后，scan_worker 是新对象:', win.scan_worker)

    # 3) 等所有扫描结束
    for _ in range(40):
        app.processEvents()
        time.sleep(0.2)
        if not win.scan_worker.isRunning():
            break

    snap(win, '最终状态（营B 的课表）')
    print('\n营B 期望：只有 A 开头 stem 命中的才标已存在')
    print('实际：')


if __name__ == '__main__':
    main()
