# -*- coding: utf-8 -*-
"""v1.5.0 专项回归（离线，不联网 / 不下载 / 不碰用户真实目录）。

覆盖用户 2026-11-07 提出的 5 点：
  1. 营列表勾选 / 全选 → 勾选的营课程合并进课程列表
  2. 课程列表第一列「标题前缀」= 原营内序号（多营合并不重排）
  3. 重新加载课程表时「进度」列恢复实际进度，不留空
  4. 多营名用「·」分隔、向左循环滚动
  5. 进入封装阶段释放网络槽位 → 立刻并行开始下一节（流水线）

外加：每行绑定所属营（输出目录 / 已下载检测不串台）、暂停不放行、
全局汇总显示「下载 / 封装」拆分。

跑法：
    python _lel/api/test_v150.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_v150_test_home'))

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QApplication, QListWidgetItem)

import xqd_gui
import xqd_platform
import xqd_history

xqd_gui.MainWindow.auto_check_auth = lambda self: None

PASS = [0]
FAIL = []
STARTED = []


def ok(name, cond, info=''):
    if cond:
        PASS[0] += 1
        print('  [PASS] %s' % name)
    else:
        FAIL.append(name)
        print('  [FAIL] %s   %s' % (name, info))


class FakeWorker(QObject):
    """假的下载线程：只记录「被启动」，绝不联网、不起真线程。"""

    progress = Signal(int, int, int, float, float)
    completed = Signal(int, bool, str, str)
    phase = Signal(int, str)
    log = Signal(str)

    def __init__(self, platform, camp, lesson, out_path, quality, job_id,
                 control=None, seg_dir=None, parent=None):
        QObject.__init__(self)
        self.job_id = job_id

    def start(self):
        STARTED.append(self.job_id)

    def isRunning(self):
        return False

    def wait(self, ms=0):
        return True


xqd_gui.DownloadWorker = FakeWorker


class FakePlatform(object):
    camp_kinds = ['正式营', '体验营']

    def __init__(self, camps, n=3):
        self.camps = camps
        self.catalogs = {}
        for c in camps:
            self.catalogs[c.name] = []
            for i in range(n):
                le = xqd_platform.Lesson(
                    index=i, title='%s-第%d节' % (c.name, i + 1),
                    when='2026.01.01', duration=100, ltype='VIDEO',
                    camp=c.name)
                le.when_date = '2026.01.0%d' % (i % 9 + 1)
                self.catalogs[c.name].append(le)

    def list_camps(self, kind='正式营'):
        return list(self.camps)

    def camp_catalog(self, camp):
        return list(self.catalogs[camp.name])

    def resolve(self, camp, lesson):
        return 'http://example.invalid/x.m3u8'


def make_camps(names=None):
    names = names or ['道德经诵读', '五行养生音乐', '太极功法巩固班']
    return [xqd_platform.Camp(n, 'c%d' % i, '正式营', 3, '正式营')
            for i, n in enumerate(names)]


def make_win(camps, n=3):
    win = xqd_gui.MainWindow()
    out = tempfile.mkdtemp(prefix='xqd_v150_out_')
    win.out_dir = out
    win.ed_out.setText(out)
    win.cookie = 'x'
    win.platform = FakePlatform(camps, n)
    win.camps = list(camps)
    win.current_camp = camps[0]
    # 关掉后台扫描线程：这些测试只关心同步可见的界面状态
    win._scan_existing = lambda *a, **k: None
    return win


def fill_camp_list(win, camps):
    win.lst_camps.blockSignals(True)
    win.lst_camps.clear()
    for c in camps:
        it = QListWidgetItem(c.name)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        it.setCheckState(Qt.Unchecked)
        win.lst_camps.addItem(it)
    win.lst_camps.blockSignals(False)
    win._sync_all_camps_checkbox()


# ── 1. 列结构 / 单营序号 ─────────────────────────────────────
def test_columns(camps):
    print('\n[1] 列结构与「标题前缀」')
    win = make_win(camps, 3)
    try:
        heads = [win.tbl_lessons.horizontalHeaderItem(i).text()
                 for i in range(win.tbl_lessons.columnCount())]
        ok('课程列表 6 列', win.tbl_lessons.columnCount() == 6,
           str(win.tbl_lessons.columnCount()))
        ok('表头顺序（含标题前缀）',
           heads == ['', '标题前缀', '课程', '标题后缀', '时长', '进度'],
           str(heads))
        ok('列常量单一事实来源',
           (xqd_gui.COL_CHECK, xqd_gui.COL_PREFIX, xqd_gui.COL_TITLE,
            xqd_gui.COL_SUFFIX, xqd_gui.COL_DUR, xqd_gui.COL_PROGRESS)
           == (0, 1, 2, 3, 4, 5))
        ok('课名列挂自绘状态词委托',
           isinstance(win.tbl_lessons.itemDelegateForColumn(
               xqd_gui.COL_TITLE), xqd_gui.LessonTitleDelegate))

        win.load_lessons()
        ok('单营 3 行', win.tbl_lessons.rowCount() == 3,
           str(win.tbl_lessons.rowCount()))
        pref = [win.tbl_lessons.item(r, xqd_gui.COL_PREFIX).text()
                for r in range(3)]
        ok('标题前缀 01/02/03', pref == ['01', '02', '03'], str(pref))
        titles = [win.tbl_lessons.item(r, xqd_gui.COL_TITLE).text()
                  for r in range(3)]
        ok('课名列只剩纯课名（无序号）',
           all(not t[:2].isdigit() for t in titles), str(titles))
        ok('每行绑定所属营',
           all(win.camp_of_row.get(r) is camps[0] for r in range(3)))
        stem = xqd_platform.lesson_stem(win.lesson_of_row[0])
        ok('序号与成品文件名前缀同源', stem.startswith('1.'), stem)
        ok('标题后缀 = 日期',
           win.tbl_lessons.item(0, xqd_gui.COL_SUFFIX).text()
           == win.lesson_of_row[0].when_date)
    finally:
        win.close()


# ── 2. 营勾选 / 全选 / 多营合并 ──────────────────────────────
def test_multi_camp(camps):
    print('\n[2] 营勾选 / 全选 / 多营合并')
    win = make_win(camps, 3)
    try:
        fill_camp_list(win, camps)
        win._on_all_camps_changed(Qt.Checked)
        ok('全选勾上全部营', len(win._checked_camps()) == len(camps),
           str(len(win._checked_camps())))
        ok('全选框 = Checked',
           win.chk_all_camps.checkState() == Qt.Checked)
        win._on_all_camps_changed(Qt.Unchecked)
        ok('再点一次取消全选', len(win._checked_camps()) == 0)

        win.lst_camps.item(0).setCheckState(Qt.Checked)
        win.lst_camps.item(1).setCheckState(Qt.Checked)
        ok('部分勾选 → 全选框三态',
           win.chk_all_camps.checkState() == Qt.PartiallyChecked)
        picked = win._checked_camps()
        ok('勾选营按列表顺序',
           [c.name for c in picked] == [camps[0].name, camps[1].name],
           str([c.name for c in picked]))

        captured = []
        win._camp_target = []
        orig = win._load_camps_lessons
        win._load_camps_lessons = lambda cs, sync=False: captured.append(
            list(cs))
        win._rebuild_lessons_from_camps()
        win._load_camps_lessons = orig
        ok('勾选变化会重建课程表',
           bool(captured) and [c.name for c in captured[0]]
           == [camps[0].name, camps[1].name], str(captured))

        win._load_camps_lessons(picked, sync=True)
        ok('合并后 6 行', win.tbl_lessons.rowCount() == 6,
           str(win.tbl_lessons.rowCount()))
        pref = [win.tbl_lessons.item(r, xqd_gui.COL_PREFIX).text()
                for r in range(6)]
        ok('★ 序号保持原营序号（不按合并行号重排）',
           pref == ['01', '02', '03', '01', '02', '03'], str(pref))
        ok('每行记住自己的营',
           [win.camp_of_row[r].name for r in range(6)]
           == [camps[0].name] * 3 + [camps[1].name] * 3)
        ok('row_of_lesson 不串台', len(win.row_of_lesson) == 6,
           str(len(win.row_of_lesson)))
        d0 = os.path.dirname(win._out_path_for(
            win.camp_of_row[0], win.lesson_of_row[0]))
        d3 = os.path.dirname(win._out_path_for(
            win.camp_of_row[3], win.lesson_of_row[3]))
        ok('输出目录按营分开', d0 != d3 and
           os.path.basename(d0) == camps[0].name and
           os.path.basename(d3) == camps[1].name,
           '%s | %s' % (d0, d3))
    finally:
        win.close()


# ── 3. 多营名跑马灯 ─────────────────────────────────────────
def test_marquee():
    print('\n[3] 多营名「·」分隔 / 向左循环滚动')
    names = ['道德经诵读与养生实修长期班第一二三四期合编甲',
             '五行养生音乐与太极功法进阶研习长期班乙',
             '太极养正十三式复训与巩固提高班丙']
    camps = make_camps(names)
    win = make_win(camps, 2)
    try:
        win._load_camps_lessons(camps, sync=True)
        label = win.lbl_lessons
        ok('分隔符是中文间隔号', xqd_gui.CAMP_SEPARATOR == ' · ')
        ok('标题含 · 分隔', xqd_gui.CAMP_SEPARATOR in label.text(),
           label.text())
        ok('标题含全部营名', all(n in label.text() for n in names))
        ok('长标题启动滚动', label._scroll and label._timer.isActive(),
           'scroll=%s w=%d' % (label._scroll, label._loop_w))
        ok('tooltip 列出全部营名',
           all(n in label.toolTip() for n in names))
        label._offset = 0
        for _ in range(5):
            label._tick()
        ok('向左移动', label._offset == 5, str(label._offset))
        label._offset = label._loop_w - 1
        label._tick()
        ok('滚满一圈回到 0', label._offset == 0, str(label._offset))

        win._update_lesson_title([camps[0]], 2)
        ok('单营不滚动', not win.lbl_lessons._scroll
           and not win.lbl_lessons._timer.isActive())
        ok('单营标题仍带营名', camps[0].name in win.lbl_lessons.text())
    finally:
        win.close()


# ── 4. 进度列恢复实际进度 ───────────────────────────────────
def test_progress(camps):
    print('\n[4] 重新加载课程表后恢复实际进度')
    win = make_win(camps[:2], 3)
    try:
        win._load_camps_lessons(camps[:2], sync=True)
        paths = [win._out_path_for(win.camp_of_row[r], win.lesson_of_row[r])
                 for r in range(6)]

        def rec(path, **kw):
            d = dict(path=path, title=os.path.basename(path), camp='',
                     state='', size=0, down=0, total=0,
                     done_dur=0.0, total_dur=0.0, duration=100)
            d.update(kw)
            win.history[path] = d

        rec(paths[0], state='已完成', down=100, total=100,
            done_dur=100, total_dur=100)
        rec(paths[1], state='下载中', down=30, total=100,
            done_dur=30, total_dur=100)
        rec(paths[2], state='失败', total=1000, down=0)
        parts = xqd_history.parts_dir_for(paths[2])
        os.makedirs(parts, exist_ok=True)
        with open(os.path.join(parts, '00000_a.ts'), 'wb') as f:
            f.write(b'x' * 250)
        os.makedirs(os.path.dirname(paths[3]), exist_ok=True)
        with open(paths[3], 'wb') as f:
            f.write(b'x' * 20000)
        win.jobs[77] = {'lesson': win.lesson_of_row[4],
                        'unit': 'dur', 'done_dur': 80.0, 'total_dur': 100.0,
                        'down': 0, 'total': 0, 'finished': False}

        # ★ 关键：重新加载，进度不能变空
        win._load_camps_lessons(camps[:2], sync=True)
        vals = [win.tbl_lessons.cellWidget(r, xqd_gui.COL_PROGRESS).value()
                for r in range(6)]
        ok('已完成 → 100%', vals[0] == 100, str(vals))
        ok('历史未完成 → 30%', vals[1] == 30, str(vals))
        ok('分片缓存 → 25%', vals[2] == 25, str(vals))
        ok('磁盘成品（无历史）→ 100%', vals[3] == 100, str(vals))
        ok('活动任务 → 80%', vals[4] == 80, str(vals))
        ok('从未下过 → 0%', vals[5] == 0, str(vals))
        ok('进度条有说明 tooltip',
           bool(win.tbl_lessons.cellWidget(1, xqd_gui.COL_PROGRESS)
                .toolTip()))

        win._mark_existing(5, True, {'path': paths[5], 'size': 20000})
        ok('扫描判定「已存在」→ 100%',
           win.tbl_lessons.cellWidget(5, xqd_gui.COL_PROGRESS).value() == 100)
        win._mark_existing(5, False, {'path': paths[5],
                                      'reason': '时长不符'})
        ok('扫描判定「需重下」→ 不留满格',
           win.tbl_lessons.cellWidget(5, xqd_gui.COL_PROGRESS).value() == 0)
    finally:
        win.close()


# ── 5. 封装阶段释放网络槽位 ─────────────────────────────────
def test_pipeline(camps):
    print('\n[5] 封装阶段释放网络槽位（流水线）')
    STARTED[:] = []
    win = make_win(camps[0:1], 6)
    try:
        win._load_camps_lessons(camps[0:1], sync=True)
        picked = [(r, le) for r, le in win.lesson_of_row.items()]
        win._start_downloads(picked)
        lim = xqd_gui.MAX_LESSON_WORKERS
        ok('初始只启动 3 个网络任务', len(STARTED) == lim,
           str(len(STARTED)))
        ok('其余 3 个排队', len(win.pending_queue) == 3,
           str(len(win.pending_queue)))
        ok('初始网络槽位占满', win._net_active() == lim,
           str(win._net_active()))

        a, b, c = STARTED[0], STARTED[1], STARTED[2]
        # ① A 进入封装：网络立刻还回去，队列放行第 4 节
        win._on_phase(a, '封装')
        ok('A 释放网络槽位', a in win.network_released)
        # 槽位一还回去就被队列里的下一节填上了 —— 这正是流水线要的效果，
        # 所以稳态网络占用仍是 3，只是占用者从 A 换成了第 4 节。
        ok('★ 空出的槽位立刻被下一节填上',
           win._net_active() == lim
           and STARTED[3] not in win.network_released,
           'net=%d started=%s' % (win._net_active(), STARTED))
        ok('★ 封装时立刻开始第 4 节', len(STARTED) == 4,
           str(len(STARTED)))
        ok('A 仍在跑（只是不占带宽）', a in win.running_workers)

        # ② B、C 也进封装：本地封装最多 2 路，C 暂时继续占网络槽位
        win._on_phase(b, '封装')
        ok('B 释放后再开第 5 节', len(STARTED) == 5,
           str(len(STARTED)))
        win._on_phase(c, '封装')
        ok('本地封装数受 MAX_MUX_WORKERS 限制',
           len(win.network_released) == xqd_gui.MAX_MUX_WORKERS,
           str(len(win.network_released)))
        ok('C 未抢到封装槽 → 仍占网络槽位',
           c not in win.network_released and c in win.running_workers)
        ok('总线程数不超硬上限',
           len(win.running_workers)
           <= lim + xqd_gui.MAX_MUX_WORKERS,
           str(len(win.running_workers)))
        ok('网络占用仍不超上限', win._net_active() <= lim,
           str(win._net_active()))
        ok('此刻没有多开任务', len(STARTED) == 5, str(len(STARTED)))

        # ③ A 完成 → 空出封装槽，C 得以释放，再放行第 6 节
        win._on_download_completed(a, True, '测试完成',
                                   os.path.join(win.out_dir, 'a.mp4'))
        ok('完成的任务不再占任何槽位',
           a not in win.running_workers and a not in win.network_released)
        ok('★ 空出的封装槽位转给 C', c in win.network_released,
           str(sorted(win.network_released)))
        ok('★ 最后一节也被放行', len(STARTED) == 6, str(len(STARTED)))
        ok('队列已清空', len(win.pending_queue) == 0,
           str(len(win.pending_queue)))

        # ④ 全局汇总拆分显示
        win._update_global_eta()
        txt = win.lbl_task_eta.text()
        ok('汇总保留「个在跑」', '个在跑' in txt, txt)
        ok('汇总显示下载/封装拆分', '下载' in txt and '封装' in txt, txt)
        ok('汇总不含已完成任务', '已完成' not in txt, txt)

        # ⑤ 校验阶段不会重复释放 / 重复起任务
        before = len(STARTED)
        win._on_phase(c, '校验')
        ok('校验阶段不重复起任务', len(STARTED) == before,
           str(len(STARTED)))
    finally:
        win.close()


def test_pipeline_paused(camps):
    print('\n[6] 暂停期间不放行新任务，继续后补上')
    STARTED[:] = []
    win = make_win(camps[0:1], 5)
    try:
        win._load_camps_lessons(camps[0:1], sync=True)
        win._start_downloads([(r, le)
                              for r, le in win.lesson_of_row.items()])
        ok('初始 3 个在跑 / 2 个排队',
           len(STARTED) == 3 and len(win.pending_queue) == 2)
        win.control.pause()
        win._paused = True
        win._on_phase(STARTED[0], '封装')
        ok('暂停中：槽位记账照常释放',
           STARTED[0] in win.network_released)
        ok('★ 暂停中不启动新任务', len(STARTED) == 3,
           str(len(STARTED)))
        win.toggle_pause()          # 继续 → _resume_states + _pump_queue
        ok('继续后立刻补上任务', len(STARTED) == 4,
           str(len(STARTED)))
        ok('继续后已解除暂停', not win.control.is_paused())
    finally:
        win.close()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    xqd_gui._apply_cjk_font(app)
    camps = make_camps()
    test_columns(camps)
    test_multi_camp(camps)
    test_marquee()
    test_progress(camps)
    test_pipeline(camps)
    test_pipeline_paused(camps)
    print('\n%d 通过 / %d 失败' % (PASS[0], len(FAIL)))
    if FAIL:
        print('失败项：' + '、'.join(FAIL))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
