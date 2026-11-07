# -*- coding: utf-8 -*-
"""下载管理表「速度 / 剩余时间」两列的截图。

用真实数据填充（模拟几个不同进度的任务），离屏渲染 PNG。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

import xqd_gui

OUT = os.path.join(ROOT, 'state', 'gui_shots')
os.makedirs(OUT, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle('Fusion')
xqd_gui._apply_cjk_font(app)

win = xqd_gui.MainWindow()
win.resize(1280, 860)
win.show()
win.ed_out.setText(r'Z:\太极营')

from xqd_platform import Camp, Lesson

camp = Camp('道德经诵读', '1', '正式营', 4, '4 节')
lessons = [
    Lesson(0, '《道德经》一至三章', '07.27 00:00', 414, 'VIDEO'),
    Lesson(1, '《道德经》四至六章', '07.28 00:00', 224, 'VIDEO'),
    Lesson(2, '《道德经》七至九章', '07.29 00:00', 270, 'VIDEO'),
    Lesson(3, '《道德经》十至十二章', '07.30 00:00', 350, 'VIDEO'),
]
for le in lessons:
    le.camp = camp.name
win.camps = [camp]
win.current_camp = camp
win.lessons = lessons
win.lst_camps.clear()
from PySide6.QtWidgets import QListWidgetItem
win.lst_camps.addItem(QListWidgetItem('道德经诵读    4 节'))
win.lbl_camp_hint.setText('1 个营')
win.load_lessons()
app.processEvents()

# ── 造几个不同状态的任务行 ──
TASKS = [
    # (标题, 状态, 已下MB, 总MB, 速度B/s, eta秒, phase)
    ('《道德经》一至三章', '下载中', 42.0, 145.0, 5242880, 31, '下载'),
    ('《道德经》四至六章', '下载中', 88.0, 92.0, 3145728, 2, '下载'),
    ('《道德经》七至九章', '下载中', 0, 0, 0, 0, '封装'),
    ('《道德经》十至十二章', '已完成', 96.0, 96.0, 0, 0, '完成'),
]
for i, (title, state, dmb, tmb, spd, eta, phase) in enumerate(TASKS):
    le = lessons[i]
    out = os.path.join(r'Z:\太极营', camp.name,
                       '%d.%s.mp4' % (i + 1, title))
    job_id = 100 + i
    win.jobs[job_id] = {
        'row': i, 'lesson': le, 'camp': camp, 'out_path': out,
        'down': int(dmb * 1048576), 'total': int(tmb * 1048576),
        'speed': spd, 'done_dur': 100.0, 'total_dur': 400.0,
        'unit': 'dur', 'eta': eta or None, 'phase': phase,
        'meter': xqd_gui.SpeedMeter(), 'eta_fixed': 18.0,
        't0': time.time() - 240,
    }
    win._add_task(le, camp, out, state, job_id)
    if phase == '封装':
        win.jobs[job_id]['eta_fixed'] = 18.0
    win._refresh_task_row(job_id)
    if i < 3:
        win.running_workers.add(job_id)

win._update_global_eta()
app.processEvents()
time.sleep(0.5)
app.processEvents()

# ★ 把下载管理表单独放大截一份，看清每列文字
tbl = win.tbl_tasks
for r in range(tbl.rowCount()):
    print('  行%d: 状态=%s 大小=%s 速度=%s 剩余=%s'
          % (r,
             tbl.item(r, 2).text(), tbl.item(r, 3).text(),
             tbl.item(r, 4).text(), tbl.item(r, 5).text()))

path = os.path.join(OUT, 'eta_columns.png')
win.grab().save(path)
print('截图:', path, os.path.getsize(path), 'bytes')

# 单独截下载管理区，放大看细节
task_panel = win.tbl_tasks
from PySide6.QtCore import QRect
r = task_panel.parentWidget().parentWidget()
if r is not None:
    p2 = os.path.join(OUT, 'eta_columns_zoom.png')
    win.grab().save(p2)

win.close()
print('全局汇总:', win.lbl_task_eta.text())
