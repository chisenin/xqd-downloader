# -*- coding: utf-8 -*-
"""生成带「暂停」按钮的界面截图（供文档/交付用）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

import xqd_gui
import xqd_platform

OUT = os.path.join(ROOT, 'state', 'gui_shots')
SHOTS = os.path.join(OUT, '50_带暂停按钮.png')
os.makedirs(OUT, exist_ok=True)


def fake_lesson(i, camp='测试营'):
    le = xqd_platform.Lesson(
        index=i, title='第%d讲 示例课程名称' % (i + 1),
        when='07.%02d 06:00' % (i + 1), duration=600, ltype='VIDEO',
        topic_id='t%d' % i, room_id='r%d' % i, camp=camp)
    le.when_date = '2026.07.%02d' % (i + 1)
    return le


class FakePlatform(object):
    platform_id = 'fake'
    display_name = '假平台'
    camp_kinds = ('正式营',)

    def __init__(self):
        self.lessons = [fake_lesson(i) for i in range(12)]
        self.camp = xqd_platform.Camp('示例营', 'c1', '正式营', 12, '12节')

    def list_camps(self, kind='正式营'):
        return [self.camp]

    def camp_catalog(self, camp):
        return self.lessons

    def resolve(self, camp, lesson):
        return 'http://example.com/x.m3u8'


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    win = xqd_gui.MainWindow()
    win.resize(1220, 800)
    win.cookie = 'fake=1'
    win.platform = FakePlatform()
    win.auto_check_auth = lambda: None
    win.current_camp = win.platform.camp
    win.camps = [win.platform.camp]
    win.load_lessons()
    win.show()
    app.processEvents()

    # 造两个「下载中」和一个「排队中」，让暂停按钮亮起来
    for i in (0, 1):
        le = win.lessons[i]
        le.state = 'running'
        win._set_row_state(i, '下载中…', None)
        cb = win.tbl_lessons.item(i, 0)
        if cb:
            cb.setCheckState(Qt.Checked)
        bar = win.tbl_lessons.cellWidget(i, 4)
        if bar:
            bar.setValue(40 + i * 25)
    win.lessons[2].state = 'queued'
    win._set_row_state(2, '排队中', None)
    win.tbl_lessons.item(2, 0).setCheckState(Qt.Checked)

    win.pending_queue.append((9001, win.lessons[2], win.current_camp,
                               'Z:\\太极营\\示例营\\3.x.mp4', 'max'))
    win.running_workers.add(9001)
    win.jobs[9001] = {'row': 2, 'lesson': win.lessons[2],
                       'camp': win.current_camp,
                       'out_path': 'Z:\\太极营\\示例营\\3.x.mp4'}
    win._sync_pause_button()
    app.processEvents()

    win.grab().save(SHOTS)
    print('saved', SHOTS)
    print('暂停按钮：enabled=%s text=%s'
          % (win.btn_pause.isEnabled(), win.btn_pause.text()))


if __name__ == '__main__':
    main()
