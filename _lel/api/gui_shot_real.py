# -*- coding: utf-8 -*-
"""真实窗口模式截图：验证中文字体与最终视觉。

窗口会短暂弹出（几秒）后自动退出。
"""
import os
import tempfile
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui

OUT = os.path.join(ROOT, 'state', 'gui_shots')
os.makedirs(OUT, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle('Fusion')
xqd_gui._apply_cjk_font(app)

win = xqd_gui.MainWindow()
win.resize(1280, 860)
win.show()


def shot(name):
    app.processEvents()
    time.sleep(0.6)
    app.processEvents()
    path = os.path.join(OUT, name + '.png')
    win.grab().save(path)
    print('截图:', os.path.basename(path),
          os.path.getsize(path), 'bytes')


def s1():
    win._on_auth_ok('userId=<USER_ID>; rsessionId=<RSESSION_ID>')
    from xqd_platform import Camp, Lesson
    from PySide6.QtWidgets import QTableWidgetItem

    camps = [Camp('道德经诵读', '1', '正式营', 27, '27 节'),
             Camp('太极功法巩固班', '2', '正式营', 4, '4 节'),
             Camp('静坐内观-身心共养计划', '3', '正式营', 61, '61 节'),
             Camp('引气归源太极营', '4', '正式营', 70, '70 节')]
    win.camps = camps
    win.lst_camps.clear()
    from PySide6.QtWidgets import QListWidgetItem
    for c in camps:
        win.lst_camps.addItem(QListWidgetItem('%s    %s' % (c.name, c.badge)))
    win.lbl_camp_hint.setText('%d 个营' % len(camps))

    samples = [
        ('《道德经》一至三章', 414, 'VIDEO', '07.27 00:00', '2026.07.27'),
        ('《道德经》四至六章', 224, 'VIDEO', '07.28 00:00', '2026.07.28'),
        ('《道德经》七至九章', 270, 'VIDEO', '07.29 00:00', '2026.07.29'),
        ('晨练课堂：静坐颂钵和声能调控', 1800, 'INTELLIGENT_LIVE',
         '07.30 06:00', '2026.07.30'),
        ('【赠】李老师四正法领读《清静经》-视频版', 900, 'VIDEO',
         '07.31 06:00', '2026.07.31'),
        ('五行养生音乐·紫竹调', 1064, 'AUDIO', '08.01 12:00', '2026.08.01'),
        ('第四课 《掤捋挤按》', 3600, 'VIDEO', '08.02 06:00', '2026.08.02'),
        ('第五课 《单鞭和云手》', 3600, 'VIDEO', '08.03 06:00', '2026.08.03'),
    ]
    lessons = []
    for i, (t, d, ty, w, wd) in enumerate(samples):
        le = Lesson(index=i, title=t, when=w, duration=d, ltype=ty,
                    camp='道德经诵读')
        le.when_date = wd
        lessons.append(le)

    win.current_camp = camps[0]
    win.lessons = lessons
    win.row_of_lesson = {le.key: i for i, le in enumerate(lessons)}
    win.lesson_of_row = {i: le for i, le in enumerate(lessons)}
    win.used_names = {'道德经诵读': set()}
    win.tbl_lessons.setRowCount(len(lessons))
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
        win.tbl_lessons.setCellWidget(i, 4, xqd_gui.CellProgressBar())

    win.lbl_lessons.setText('课程列表 · 道德经诵读（%d 节）' % len(lessons))
    win.lbl_lesson_hint.setText(
        '共 %d 节 · 目录：%s' % (len(lessons),
                                os.path.join(win.out_dir, '道德经诵读')))

    # 进度与状态
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

    for le, state, size in (
            (lessons[2], '已完成', '20.5 MB'),
            (lessons[0], '下载中', ''),
            (lessons[3], '失败', ''),
            (lessons[4], '已完成', '86.3 MB')):
        win._add_task(le, '道德经诵读',
                      'Z:\\太极营\\道德经诵读\\%02d.x.mp4' % le.index, state)
        r = win.tbl_tasks.rowCount() - 1
        win.tbl_tasks.setItem(r, 3, QTableWidgetItem(size))

    win.log('授权成功，可以关闭模拟器与 App。')
    win.log('加载正式营：9 个')
    win.log('开始下载：道德经诵读 / 《道德经》四至六章')
    win.log('完成：《道德经》一至三章（标准 HLS，20.5 MB）')
    win.log('失败：《道德经》七至九章 —— 时长不符（已重新勾选）')
    shot('10_真实界面_完整状态')


steps = [s1]
state = {'i': 0}


def run_next():
    if state['i'] >= len(steps):
        app.quit()
        return
    fn = steps[state['i']]
    state['i'] += 1
    try:
        fn()
    except Exception:
        import traceback
        traceback.print_exc()
    QTimer.singleShot(150, run_next)


QTimer.singleShot(900, run_next)
app.exec_()
print('完成')
