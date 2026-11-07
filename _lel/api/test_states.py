# -*- coding: utf-8 -*-
"""三处状态一一对应 —— v1.3.1 新功能专项测试。

用户 2026-11-07 指出（附截图）：

  「三处地方的状态应当能一一对应」

  红框标了三处：
    ① 课程列表的「标题后缀」列   —— 截图里写「【下载中…】」
    ② 下载管理表的「状态」列     —— 截图里写「封装中」
    ③ 运行日志                   —— 截图里只有「开始下载：xxx」

  实测矛盾：第 34 行「晚间课堂：五种意志力+阶段性回顾」
    在课程列表说「下载中…」，在下载管理表说「封装中」—— 对不上号。
    日志里则根本查不到当前状态。

本文件**不联网**，全部用假数据。
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_history

PASS = []
FAIL = []

OUT = os.path.join(tempfile.gettempdir(), 'xqd_test_states')


def ok(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('OK  ' if cond else 'FAIL', name,
                       ('  -> %s' % (extra,)) if extra else ''))


class FakeLesson(object):
    def __init__(self, title, dur=120, idx=0):
        self.title = title
        self.duration = dur
        self.when = '2025-03-12 06:00'
        self.type = 'VIDEO'
        self.key = '%s#%d' % (title, idx)
        self.out_path = ''
        self.state = ''


class FakeCamp(object):
    name = '测试营'


class FakePlatform(object):
    def __init__(self, lessons):
        self.camp = FakeCamp()
        self._lessons = lessons

    def camp_catalog(self, camp):
        return list(self._lessons)


def build_gui(app):
    """造一个不联网的窗口。"""
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

    lessons = [FakeLesson('第一讲', idx=0), FakeLesson('第二讲', idx=1),
               FakeLesson('第三讲', idx=2)]
    win.platform = FakePlatform(lessons)
    win.current_camp = win.platform.camp
    win.camps = [win.platform.camp]
    win.load_lessons()
    app.processEvents()
    return win


def suffix_of(win, row):
    """课程列表第 row 行**跟在课名后面**的状态词。

    ★ v1.4.0 起状态词不再单独占一列，而是存在课名 item 的
      STATE_ROLE 上（由 LessonTitleDelegate 画在课名后面）。
    """
    it = win.tbl_lessons.item(row, 1)
    if it is None:
        return ''
    return it.data(xqd_gui.STATE_ROLE) or ''


def task_state(win, job_id):
    """下载管理表里某任务的状态列文字。"""
    r = win._task_row_of_job.get(job_id)
    if r is None or r >= win.tbl_tasks.rowCount():
        return ''
    it = win.tbl_tasks.item(r, 2)
    return it.text() if it else ''


def log_texts(win):
    return win.txt_log.toPlainText()


# ══════════════════════════════════════════════════════════════
#  1. 状态词表 —— 单一事实来源
# ══════════════════════════════════════════════════════════════

def test_state_table():
    print('\n──── 1. 状态词表 ────')

    ok('PHASE_TEXT 覆盖四个阶段',
       set(xqd_gui.PHASE_TEXT.keys()) == {'解析', '下载', '封装', '校验'},
       str(sorted(xqd_gui.PHASE_TEXT.keys())))

    ok('PHASE_TEXT 的值都是「…中」',
       all(v.endswith('中') for v in xqd_gui.PHASE_TEXT.values()),
       str(xqd_gui.PHASE_TEXT))

    ok('阶段词都出现在界面状态词全集里',
       all(v in xqd_gui.STATE_TEXTS for v in xqd_gui.PHASE_TEXT.values()),
       str(xqd_gui.STATE_TEXTS))

    ok('四个阶段词都有配色',
       all(v in xqd_gui.STATE_COLORS
           for v in xqd_gui.PHASE_TEXT.values()),
       str(sorted(xqd_gui.STATE_COLORS.keys())))

    # ★ 每个界面状态词都必须有配色 —— 少一个就会出现「后缀文字变白」
    missing = [s for s in xqd_gui.STATE_TEXTS
               if s not in xqd_gui.STATE_COLORS]
    ok('状态词全都有配色（无遗漏）', not missing, str(missing))


# ══════════════════════════════════════════════════════════════
#  2. 课程列表后缀随阶段实时变化
# ══════════════════════════════════════════════════════════════

def test_suffix_follows_phase(app):
    print('\n──── 2. 课程列表后缀随阶段变 ────')

    win = build_gui(app)
    le = win.lessons[0]
    row = win._row_of_lesson_obj(le)
    ok('课程行可定位', row is not None, str(row))

    # 模拟：任务已入队并开始
    job_id = 9001
    win.jobs[job_id] = {'row': row, 'lesson': le, 'camp': win.current_camp,
                        'out_path': os.path.join(OUT, 'a.mp4'),
                        'down': 0, 'total': 0, 'speed': 0.0,
                        'done_dur': 0.0, 'total_dur': 0.0,
                        'unit': 'dur', 'eta': None, 'phase': '',
                        'meter': xqd_gui.SpeedMeter(),
                        'bmeter': xqd_gui.SpeedMeter(),
                        'rate_dur': 0.0, 'seg_dir': '',
                        'cached_bytes': 0, 'cached_segs': 0,
                        'eta_fixed': 0.0, 't0': 0}
    win._task_row_of_job[job_id] = 0
    win.tbl_tasks.insertRow(0)
    for c in range(win.tbl_tasks.columnCount()):
        win.tbl_tasks.setItem(0, c, xqd_gui.QTableWidgetItem(''))
    win.running_workers.add(job_id)

    for phase, word in (('解析', '解析中'), ('下载', '下载中'),
                        ('封装', '封装中'), ('校验', '校验中')):
        win._on_phase(job_id, phase)
        app.processEvents()
        s = suffix_of(win, row)
        ok('阶段「%s」→ 后缀显示「%s」' % (phase, word),
           s == word, s)
        ok('阶段「%s」→ 下载管理状态列同步' % phase,
           task_state(win, job_id) == word, task_state(win, job_id))
        ok('阶段「%s」→ 两处状态一致' % phase,
           s == task_state(win, job_id),
           '%s vs %s' % (s, task_state(win, job_id)))

    win.running_workers.discard(job_id)


def test_phase_logged(app):
    print('\n──── 3. 运行日志记录阶段 ────')

    win = build_gui(app)
    le = win.lessons[0]
    row = win._row_of_lesson_obj(le)
    job_id = 9002
    win.jobs[job_id] = {'row': row, 'lesson': le, 'camp': win.current_camp,
                        'out_path': os.path.join(OUT, 'b.mp4'),
                        'down': 0, 'total': 0, 'speed': 0.0,
                        'done_dur': 0.0, 'total_dur': 0.0,
                        'unit': 'dur', 'eta': None, 'phase': '',
                        'meter': xqd_gui.SpeedMeter(),
                        'bmeter': xqd_gui.SpeedMeter(),
                        'rate_dur': 0.0, 'seg_dir': '',
                        'cached_bytes': 0, 'cached_segs': 0,
                        'eta_fixed': 0.0, 't0': 0}
    win._task_row_of_job[job_id] = 0
    win.tbl_tasks.insertRow(0)
    for c in range(win.tbl_tasks.columnCount()):
        win.tbl_tasks.setItem(0, c, xqd_gui.QTableWidgetItem(''))
    win.running_workers.add(job_id)

    before = log_texts(win)
    win._on_phase(job_id, '封装')
    app.processEvents()
    after = log_texts(win)
    ok('阶段变化写进了日志', len(after) > len(before))
    ok('日志里有「封装中」', '封装中' in after,
       after.strip().splitlines()[-1] if after.strip() else '')
    ok('日志里有课名', le.title in after)

    # 阶段日志不该抢底部状态栏
    ok('阶段日志不覆盖状态栏',
       win.status_label.text() != '封装中：%s' % le.title,
       win.status_label.text())

    # 同一个阶段重复上报不该刷屏
    n1 = len(log_texts(win))
    win._on_phase(job_id, '封装')
    app.processEvents()
    ok('同阶段不重复打日志', len(log_texts(win)) == n1)

    win.running_workers.discard(job_id)


# ══════════════════════════════════════════════════════════════
#  4. 暂停 / 恢复 —— 两处状态同步
# ══════════════════════════════════════════════════════════════

def _prep_running(win, job_id=9003, phase='封装'):
    """造一个「正在封装中」的任务。"""
    le = win.lessons[0]
    row = win._row_of_lesson_obj(le)
    win.jobs[job_id] = {'row': row, 'lesson': le, 'camp': win.current_camp,
                        'out_path': os.path.join(OUT, 'c.mp4'),
                        'down': 0, 'total': 0, 'speed': 0.0,
                        'done_dur': 0.0, 'total_dur': 0.0,
                        'unit': 'dur', 'eta': None, 'phase': phase,
                        'meter': xqd_gui.SpeedMeter(),
                        'bmeter': xqd_gui.SpeedMeter(),
                        'rate_dur': 0.0, 'seg_dir': '',
                        'cached_bytes': 0, 'cached_segs': 0,
                        'eta_fixed': 0.0, 't0': 0}
    win._task_row_of_job[job_id] = 0
    win.tbl_tasks.insertRow(0)
    for c in range(win.tbl_tasks.columnCount()):
        win.tbl_tasks.setItem(0, c, xqd_gui.QTableWidgetItem(''))
    win.running_workers.add(job_id)
    win._set_both_states(job_id, xqd_gui.PHASE_TEXT[phase])
    return le, row, job_id


def test_pause_sync(app):
    print('\n──── 4. 暂停 / 恢复同步 ────')

    win = build_gui(app)
    le, row, job_id = _prep_running(win)
    app.processEvents()
    ok('准备状态：后缀是「封装中」',
       suffix_of(win, row) == '封装中', suffix_of(win, row))
    ok('准备状态：状态列是「封装中」',
       task_state(win, job_id) == '封装中', task_state(win, job_id))

    # 暂停
    win._paused = True
    win._set_all_running_state('已暂停')
    app.processEvents()
    ok('暂停后课程列表后缀 =「已暂停」',
       suffix_of(win, row) == '已暂停', suffix_of(win, row))
    ok('暂停后下载管理状态列 =「已暂停」',
       task_state(win, job_id) == '已暂停', task_state(win, job_id))
    ok('暂停后两处一致',
       suffix_of(win, row) == task_state(win, job_id),
       '%s vs %s' % (suffix_of(win, row), task_state(win, job_id)))

    # 定时刷新不能把「已暂停」冲掉（守卫：已暂停不在 PHASE_TEXTS 里）
    win._refresh_task_row(job_id)
    app.processEvents()
    ok('定时刷新不覆盖「已暂停」',
       task_state(win, job_id) == '已暂停', task_state(win, job_id))

    # 恢复 —— 应回到**真实阶段**（封装中），不是笼统的「下载中」
    win._paused = False
    win._resume_states()
    app.processEvents()
    ok('恢复后回到真实阶段「封装中」',
       suffix_of(win, row) == '封装中', suffix_of(win, row))
    ok('恢复后下载管理状态列也回到「封装中」',
       task_state(win, job_id) == '封装中', task_state(win, job_id))
    ok('恢复后两处一致',
       suffix_of(win, row) == task_state(win, job_id),
       '%s vs %s' % (suffix_of(win, row), task_state(win, job_id)))

    win.running_workers.discard(job_id)


# ══════════════════════════════════════════════════════════════
#  5. 完成 / 失败 —— 两处一致
# ══════════════════════════════════════════════════════════════

def test_finish_sync(app):
    print('\n──── 5. 完成 / 失败两处一致 ────')

    win = build_gui(app)
    le, row, job_id = _prep_running(win, job_id=9004, phase='下载')
    app.processEvents()

    win._on_download_completed(job_id, True, 'ok', os.path.join(OUT, 'd.mp4'))
    app.processEvents()
    ok('完成后课程列表后缀 =「已完成」',
       suffix_of(win, row) == '已完成', suffix_of(win, row))
    ok('完成后下载管理状态列 =「已完成」',
       task_state(win, job_id) == '已完成', task_state(win, job_id))
    ok('完成后两处一致',
       suffix_of(win, row) == task_state(win, job_id),
       '%s vs %s' % (suffix_of(win, row), task_state(win, job_id)))
    ok('完成日志用「已完成」', '已完成' in log_texts(win))

    # 失败
    win2 = build_gui(app)
    le2, row2, jid2 = _prep_running(win2, job_id=9005, phase='下载')
    app.processEvents()
    win2._on_download_completed(jid2, False, '断了', '')
    app.processEvents()
    ok('失败后课程列表后缀 =「失败」',
       suffix_of(win2, row2) == '失败', suffix_of(win2, row2))
    ok('失败后下载管理状态列 =「失败」',
       task_state(win2, jid2) == '失败', task_state(win2, jid2))


# ══════════════════════════════════════════════════════════════
#  6. 排队的课不出现在下载管理表
# ══════════════════════════════════════════════════════════════

def test_queued_not_in_tasks(app):
    print('\n──── 6. 排队中的课 ────')

    win = build_gui(app)
    le = win.lessons[1]
    row = win._row_of_lesson_obj(le)
    win._set_row_state(row, '排队中', None)
    app.processEvents()
    ok('排队中的课后缀 =「排队中」',
       suffix_of(win, row) == '排队中', suffix_of(win, row))
    ok('「排队中」有配色',
       '排队中' in xqd_gui.STATE_COLORS)


# ══════════════════════════════════════════════════════════════
#  7. 终态守卫 —— 迟到的阶段信号不能改回终态
# ══════════════════════════════════════════════════════════════

def test_terminal_guard(app):
    print('\n──── 7. 终态守卫 ────')

    win = build_gui(app)
    le, row, job_id = _prep_running(win, job_id=9006, phase='下载')
    app.processEvents()

    # 完成（走真实的完成回调）
    win._on_download_completed(job_id, True, 'ok', os.path.join(OUT, 'e.mp4'))
    app.processEvents()
    ok('完成后状态列 =「已完成」',
       task_state(win, job_id) == '已完成', task_state(win, job_id))
    ok('完成后课程列表后缀 =「已完成」',
       suffix_of(win, row) == '已完成', suffix_of(win, row))

    # 迟到的阶段信号
    win._on_phase(job_id, '下载')
    app.processEvents()
    ok('迟到阶段不改状态列',
       task_state(win, job_id) == '已完成', task_state(win, job_id))
    ok('迟到阶段不改课程列表后缀',
       suffix_of(win, row) == '已完成', suffix_of(win, row))

    # 失败终态同理
    win2 = build_gui(app)
    le2, row2, jid2 = _prep_running(win2, job_id=9007, phase='下载')
    app.processEvents()
    win2._on_download_completed(jid2, False, '断了', '')
    app.processEvents()
    ok('失败后状态列 =「失败」',
       task_state(win2, jid2) == '失败', task_state(win2, jid2))
    ok('失败后课程列表后缀 =「失败」',
       suffix_of(win2, row2) == '失败', suffix_of(win2, row2))
    win2._on_phase(jid2, '封装')
    app.processEvents()
    ok('失败后迟到阶段不改状态列',
       task_state(win2, jid2) == '失败', task_state(win2, jid2))
    ok('失败后迟到阶段不改课程列表后缀',
       suffix_of(win2, row2) == '失败', suffix_of(win2, row2))


def main():
    os.makedirs(OUT, exist_ok=True)
    test_state_table()

    app = QApplication(sys.argv)
    test_suffix_follows_phase(app)
    test_phase_logged(app)
    test_pause_sync(app)
    test_finish_sync(app)
    test_queued_not_in_tasks(app)
    test_terminal_guard(app)

    print('\n========================================================')
    print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：')
        for f in FAIL:
            print('  -', f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
