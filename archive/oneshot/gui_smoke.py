# -*- coding: utf-8 -*-
"""GUI 冒烟测试：离屏渲染各页面并截图，确认界面能正常构建。"""
import os
import tempfile
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state', 'gui_shots')
os.makedirs(OUT, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle('Fusion')

win = xqd_gui.MainWindow()
win.resize(1280, 860)
win.show()


def shot(name):
    app.processEvents()
    time.sleep(0.35)
    app.processEvents()
    path = os.path.join(OUT, name + '.png')
    win.grab().save(path)
    print('截图:', path, os.path.getsize(path), 'bytes')


def step1():
    print('顶栏:', win.lbl_auth.text())
    shot('01_初始_未授权')


def step2():
    # 模拟授权成功
    win._on_auth_ok('userId=<FAKE_USER_ID>; rsessionId=<FAKE_RSESSION>')
    print('授权后:', win.lbl_auth.text())
    shot('02_授权成功_横幅')


def step3():
    # 模拟营列表
    from xqd_platform import Camp, Lesson
    camps = [Camp('道德经诵读', '123', '正式营', 27, '27节'),
             Camp('太极功法巩固班', '456', '正式营', 4, '4节'),
             Camp('静坐内观-身心共养计划', '789', '正式营', 61, '61节')]
    win.camps = camps
    win.lst_camps.clear()
    for c in camps:
        win.lst_camps.addItem('%s\n%s' % (c.name, c.badge))
    win.lbl_camp_hint.setText('%d 个营' % len(camps))
    win.lst_camps.setCurrentRow(0)
    app.processEvents()
    shot('03_营列表')


def step4():
    # 模拟课表
    from xqd_platform import Lesson
    lessons = []
    samples = [
        ('《道德经》一至三章', 414, 'VIDEO', '07.27 00:00', '2026.07.27'),
        ('《道德经》四至六章', 224, 'VIDEO', '07.28 00:00', '2026.07.28'),
        ('《道德经》七至九章', 270, 'VIDEO', '07.29 00:00', '2026.07.29'),
        ('晨练课堂：静坐颂钵和声能调控', 1800, 'INTELLIGENT_LIVE',
         '07.30 06:00', '2026.07.30'),
        ('【赠】李老师四正法领读《清静经》-视频版', 900, 'VIDEO',
         '07.31 06:00', '2026.07.31'),
        ('五行养生音乐·紫竹调', 1064, 'AUDIO', '08.01 12:00', '2026.08.01'),
    ]
    for i, (t, d, ty, w, wd) in enumerate(samples):
        le = Lesson(index=i, title=t, when=w, duration=d, ltype=ty,
                    camp='道德经诵读')
        le.when_date = wd
        lessons.append(le)

    win.current_camp = win.camps[0]
    win.lessons = lessons
    win.row_of_lesson = {le.key: i for i, le in enumerate(lessons)}
    win.lesson_of_row = {i: le for i, le in enumerate(lessons)}
    win.used_names = {'道德经诵读': set()}

    win.tbl_lessons.setRowCount(len(lessons))
    from PySide6.QtWidgets import QTableWidgetItem
    for i, le in enumerate(lessons):
        cb = QTableWidgetItem('')
        cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                    | Qt.ItemIsSelectable)
        cb.setCheckState(Qt.Unchecked)
        win.tbl_lessons.setItem(i, 0, cb)
        win.tbl_lessons.setItem(
            i, 1, QTableWidgetItem('%02d  %s' % (i + 1, le.title)))
        win.tbl_lessons.setItem(i, 2, QTableWidgetItem(le.when))
        win.tbl_lessons.setItem(i, 3,
                                QTableWidgetItem(xqd_gui._fmt_dur(le.duration)))
        bar = xqd_gui.CellProgressBar()
        win.tbl_lessons.setCellWidget(i, 4, bar)

    win.lbl_lessons.setText('课程列表 · 道德经诵读（%d 节）' % len(lessons))
    win.lbl_lesson_hint.setText('共 %d 节 · 目录：%s'
                                % (len(lessons),
                                   os.path.join(win.out_dir, '道德经诵读')))
    app.processEvents()
    shot('04_课程列表')


def step5():
    # 模拟下载中的进度条 + 任务列表
    from PySide6.QtWidgets import QTableWidgetItem
    # 勾选前两节
    for r in (0, 1):
        win.tbl_lessons.item(r, 0).setCheckState(Qt.Checked)
    # 进度条
    for r, pct in ((0, 62), (1, 18)):
        bar = win.tbl_lessons.cellWidget(r, 4)
        if bar:
            bar.setValue(pct)
    win._set_row_state(0, '下载中…', '正在下载')
    win._set_row_state(1, '下载中…', '正在下载')
    win._set_row_state(2, '已完成', '标准 HLS，20.5 MB')
    win.tbl_lessons.cellWidget(2, 4).setValue(100)
    win._set_row_state(3, '失败', '时长不符：230.8s vs 期望 224.0s')
    win.tbl_lessons.item(3, 0).setCheckState(Qt.Checked)

    # 任务表
    for le, state, size in (
            (win.lessons[2], '已完成', '20.5 MB'),
            (win.lessons[0], '下载中', ''),
            (win.lessons[3], '失败', ''),
            (win.lessons[4], '已完成', '86.3 MB')):
        win._add_task(le, '道德经诵读',
                      'Z:/太极营/道德经诵读/%02d.x.mp4' % le.index, state)
        r = win.tbl_tasks.rowCount() - 1
        win.tbl_tasks.setItem(r, 3, QTableWidgetItem(size))
    app.processEvents()
    shot('05_下载进度与任务')


def step6():
    win.log('已连接：授权有效，9 个正式营')
    win.log('开始下载：道德经诵读 / 《道德经》四至六章')
    win.log('完成：《道德经》一至三章（标准 HLS，20.5 MB）')
    win.log('失败：《道德经》七至九章 —— 时长不符')
    shot('06_运行日志')


steps = [step1, step2, step3, step4, step5, step6]
state = {'i': 0}


def run_next():
    if state['i'] >= len(steps):
        print('\n全部截图完成')
        app.quit()
        return
    fn = steps[state['i']]
    state['i'] += 1
    try:
        fn()
    except Exception as e:
        import traceback
        traceback.print_exc()
    QTimer.singleShot(120, run_next)


QTimer.singleShot(500, run_next)
app.exec_()
