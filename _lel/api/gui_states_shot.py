# -*- coding: utf-8 -*-
"""GUI 渲染验证：三处状态在**真实渲染**的界面上是否一致。

这个测试不验证逻辑（test_states.py 已经验证了），
而是验证**渲染出来**的样子 —— 截图给用户看。

造一个假窗口：3 节课，其中两节在不同阶段，
渲染成 PNG，检查两张截图。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_history

OUT = os.path.join(tempfile.gettempdir(), 'xqd_test_states')
SHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'state')


class FakeLesson(object):
    def __init__(self, title, dur=120, idx=0, date='2025.03.12'):
        self.title = title
        self.duration = dur
        self.when = '2025-03-12 06:00'
        self.when_date = date
        self.type = 'VIDEO'
        self.index = idx
        self.key = '%s#%d' % (title, idx)
        self.out_path = ''
        self.state = ''


class FakeCamp(object):
    name = '静坐内观-身心共养计划'


class FakePlatform(object):
    def __init__(self, lessons):
        self.camp = FakeCamp()
        self._lessons = lessons

    def camp_catalog(self, camp):
        return list(self._lessons)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SHOT_DIR, exist_ok=True)
    app = QApplication(sys.argv)

    real_load = xqd_history.load_history
    xqd_history.load_history = lambda *a, **k: {}
    try:
        win = xqd_gui.MainWindow()
    finally:
        xqd_history.load_history = real_load

    win.ed_out.setText(OUT)
    win.out_dir = OUT
    win.cookie = 'fake=1'
    win.auto_check_auth = lambda: None

    lessons = [FakeLesson('晚间课堂：五种意志力+阶段性回顾', 6384, 0),
               FakeLesson('心读专场——道家秘传「五行导引功心读」', 7326, 1),
               FakeLesson('晚间课堂：三轮关系实践', 5805, 2)]
    win.platform = FakePlatform(lessons)
    win.current_camp = win.platform.camp
    win.camps = [win.platform.camp]
    win.load_lessons()
    app.processEvents()

    # 造三个任务，分别处在不同阶段
    stages = ['封装中', '下载中', '排队中']
    for i, (le, st) in enumerate(zip(lessons, stages)):
        jid = 8000 + i
        row = win._row_of_lesson_obj(le)
        out_path = os.path.join(OUT, '%02d.mp4' % i)
        win.jobs[jid] = {'row': row, 'lesson': le, 'camp': win.current_camp,
                         'out_path': out_path,
                         'down': 120 * 1048576, 'total': 145 * 1048576,
                         'speed': 8.4 * 1048576, 'done_dur': 3000.0,
                         'total_dur': 6384.0, 'unit': 'dur', 'eta': 900.0,
                         'phase': '封装' if i == 0 else ('下载' if i == 1 else ''),
                         'meter': xqd_gui.SpeedMeter(),
                         'bmeter': xqd_gui.SpeedMeter(),
                         'rate_dur': 40.0, 'seg_dir': '',
                         'cached_bytes': 0, 'cached_segs': 0,
                         'eta_fixed': 0.0, 't0': 0}
        win._task_row_of_job[jid] = i
        win.tbl_tasks.insertRow(i)
        for c in range(win.tbl_tasks.columnCount()):
            win.tbl_tasks.setItem(i, c, xqd_gui.QTableWidgetItem(''))
        win._set_both_states(jid, st)
        if i < 2:
            win.running_workers.add(jid)

    # 日志里也打上阶段
    win.log_state('解析中：晚间课堂：五种意志力+阶段性回顾')
    win.log_state('下载中：晚间课堂：五种意志力+阶段性回顾')
    win.log_state('封装中：晚间课堂：五种意志力+阶段性回顾')
    win.log_state('解析中：心读专场——道家秘传「五行导引功心读」')
    win.log_state('下载中：心读专场——道家秘传「五行导引功心读」')
    app.processEvents()

    # 刷新下载管理的其它列
    for jid in list(win.running_workers):
        win._refresh_task_row(jid)
    win._update_global_eta()
    app.processEvents()

    shot = os.path.join(SHOT_DIR, 'states_shot.png')
    win.grab().save(shot)
    print('截图：%s' % shot)

    # 打印核对
    print('\n课程列表状态词（跟在标题后）vs 下载管理状态列：')
    for i, le in enumerate(lessons):
        row = win._row_of_lesson_obj(le)
        s = win.tbl_lessons.item(row, 1).data(xqd_gui.STATE_ROLE) or ''
        t = win.tbl_tasks.item(i, 2).text()
        date = win.tbl_lessons.item(row, 2).text()
        flag = 'OK ' if s == t else 'BAD'
        print('  %s %-40s %-10s %-10s 标题后缀=%s'
              % (flag, le.title[:16], s, t, date))

    print('\n日志尾部：')
    for line in win.txt_log.toPlainText().splitlines()[-6:]:
        print('  ' + line)


if __name__ == '__main__':
    main()
