# -*- coding: utf-8 -*-
"""剩余时间估算（ETA）测试。

覆盖：
  1. SpeedMeter 速率计算（窗口滑动、样本过期）
  2. ETA 随速度变化（网络变慢 → 剩余时间变长）
  3. ETA 随剩余内容变化（下载推进 → 剩余时间变短）
  4. 时长占比 vs 字节占比的差异
  5. GUI 表里「剩余时间 / 速度」两列的显示
  6. 暂停时 ETA 冻结
  7. 封装阶段的估算
  8. 全局剩余时间汇总

跑法：
    python _lel/api/test_eta.py
"""

import os
import tempfile
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt

import xqd_engine
# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_platform

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'eta_out')

PASS = [0]
FAIL = []


def ok(name, cond, info=''):
    if cond:
        PASS[0] += 1
        print('  ✓ %s' % name)
    else:
        FAIL.append(name)
        print('  ✗ %s   %s' % (name, info))


def approx(a, b, tol=0.25):
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= tol


# ── 1. SpeedMeter ────────────────────────────────────────────
def test_speed_meter():
    print('\n[1] SpeedMeter 速率计算')
    m = xqd_gui.SpeedMeter(window=8.0)

    # 样本不足 → 无速率
    m.add(100, now=1000.0)
    ok('单样本时速率为 0', m.speed() == 0.0, m.speed())

    # 1000 字节 / 2 秒 = 500 B/s
    m.add(1100, now=1002.0)
    ok('两样本算出速率', approx(m.speed(now=1002.0), 500.0, 0.01),
       'got %s' % m.speed(now=1002.0))

    # 窗口滑出：8 秒前的样本应被丢弃
    m.add(1200, now=1012.0)   # 已超窗口
    ok('过期样本被剪掉', len(m.samples) <= 3, len(m.samples))

    # 数据过期（>6 秒无新进度）→ 速率归零，但 last_speed 保留
    m2 = xqd_gui.SpeedMeter(window=60.0)
    now = time.time()
    m2.add(0, now=now)
    m2.add(1000, now=now + 1)
    sp = m2.speed(now=now + 1)
    ok('有新鲜样本时速率 > 0', sp > 0, sp)
    # ★ 10 秒内没有新的进度回调 → 数据过期 → 速率归零
    ok('数据过期后速率归零', m2.speed(now=now + 10) == 0.0,
       m2.speed(now=now + 10))
    ok('但 last_speed 保留', m2.last_speed > 0, m2.last_speed)

    # 速率变慢 → 估算的剩余时间应变长
    m3 = xqd_gui.SpeedMeter(window=60.0)
    base = time.time()
    m3.add(0, now=base)
    m3.add(1000, now=base + 1)      # 1000 B/s
    fast = m3.speed(now=base + 1)
    m3.add(1100, now=base + 2)      # 100 B/s
    slow = m3.speed(now=base + 2)
    ok('速度变慢时速率下降', slow < fast, '%s -> %s' % (fast, slow))


# ── 2. ETA 随速度 / 剩余内容变化 ──────────────────────────────
def test_eta_follows_speed_and_remaining():
    print('\n[2] ETA 随速度 / 剩余内容变化')
    win = _make_win()
    try:
        # ★ speed = 字节速率（显示用）；rate_dur = 内容速率（ETA 用）
        job = {'down': 0, 'total': 1000, 'speed': 1000.0,
               'rate_dur': 100.0,
               'done_dur': 0.0, 'total_dur': 100.0, 'unit': 'dur',
               'phase': '下载', 'meter': xqd_gui.SpeedMeter(),
               'bmeter': xqd_gui.SpeedMeter(),
               'eta_fixed': 0.0}
        job['eta'] = win._compute_eta(job)
        eta1 = job['eta']
        ok('能算出剩余时间', eta1 is not None and eta1 > 0, eta1)

        # 同样的速度，剩余内容变少 → 剩余时间变短
        job['done_dur'] = 90.0
        job['eta'] = win._compute_eta(job)
        eta2 = job['eta']
        ok('剩余内容变少 → 剩余时间变短',
           eta2 < eta1, '%s -> %s' % (eta1, eta2))
        ok('剩余 10 / 速率 100 = 0.1s', approx(eta2, 0.1, 0.01), eta2)

        # 同样的剩余内容，速度变慢 → 剩余时间变长
        job['done_dur'] = 0.0
        job['rate_dur'] = 50.0
        job['eta'] = win._compute_eta(job)
        eta3 = job['eta']
        ok('速度变慢 → 剩余时间变长', eta3 > eta1,
           '%s -> %s' % (eta1, eta3))
        ok('速度减半 → 剩余时间翻倍', approx(eta3, eta1 * 2, 0.01),
           '%s vs %s' % (eta3, eta1 * 2))

        # 速率归零 → 没有估算值（显示 --），而不是报一个假的
        # 先让 meter 里有一次有效速率（模拟「刚才还在下」）
        base = time.time()
        job['meter'].add(0, now=base)
        job['meter'].add(500.0, now=base + 1)   # 500 单位/秒
        job['rate_dur'] = 0.0
        job['eta'] = win._compute_eta(job)
        ok('速率为 0 时不给估算值', job['eta'] is None, job['eta'])
        eta, _ = win._job_eta(job)
        ok('但会用 last_speed 兜底', eta is not None, eta)
        ok('兜底值 = 剩余 100 / 速率 500 = 0.2',
           eta is not None and approx(eta, 0.2, 0.01), eta)
    finally:
        win.close()


# ── 3. 时长占比 vs 字节占比 ──────────────────────────────────
def test_duration_ratio():
    print('\n[3] 时长占比 vs 字节占比')
    win = _make_win()
    try:
        win.jobs[1] = {'row': 0, 'lesson': win.lessons[0],
                       'camp': win.current_camp, 'out_path': '',
                       'down': 0, 'total': 0, 'speed': 0.0,
                       'done_dur': 0.0, 'total_dur': 0.0, 'unit': 'dur',
                       'eta': None, 'phase': '下载',
                       'meter': xqd_gui.SpeedMeter(),
                       'bmeter': xqd_gui.SpeedMeter(),
                       'rate_dur': 0.0,
                       'eta_fixed': 0.0, 't0': time.time()}
        # 模拟引擎回调：字节数是估算的，时长是精确的
        win._on_progress(1, 5000, 10000, 30.0, 300.0)
        j = win.jobs[1]
        ok('单位选为时长', j['unit'] == 'dur', j['unit'])
        ok('记录了已下载时长', abs(j['done_dur'] - 30.0) < 0.01,
           j['done_dur'])
        ok('记录了总时长', abs(j['total_dur'] - 300.0) < 0.01,
           j['total_dur'])
    finally:
        win.close()


# ── 4. GUI 表列显示 ──────────────────────────────────────────
def test_table_columns():
    print('\n[4] 下载管理表：速度 / 剩余时间两列')
    win = _make_win()
    try:
        hdr = [win.tbl_tasks.horizontalHeaderItem(i).text()
               for i in range(win.tbl_tasks.columnCount())]
        ok('列头含「速度」', '速度' in hdr, hdr)
        ok('列头含「剩余时间」', '剩余时间' in hdr, hdr)
        ok('不再叫「时间」', '时间' not in hdr, hdr)

        # 造一个任务行
        le = win.lessons[0]
        out = os.path.join(OUT, 'x.mp4')
        win.jobs[42] = {'row': 0, 'lesson': le, 'camp': win.current_camp,
                        'out_path': out, 'down': 0, 'total': 0,
                        'speed': 0.0, 'done_dur': 0.0, 'total_dur': 0.0,
                        'unit': 'dur', 'eta': None, 'phase': '',
                        'meter': xqd_gui.SpeedMeter(),
                        'bmeter': xqd_gui.SpeedMeter(),
                        'rate_dur': 0.0,
                        'eta_fixed': 0.0, 't0': time.time()}
        win._add_task(le, win.current_camp, out, '下载中', 42)
        r = win._task_row_of_job[42]
        ok('初始剩余时间为 --',
           win.tbl_tasks.item(r, 5).text() == '--',
           win.tbl_tasks.item(r, 5).text())

        # 喂进度：10 秒内容 / 100 秒内容，速率 1（秒/秒）
        win._on_progress(42, 1000, 10000, 10.0, 100.0)
        win._on_progress(42, 2000, 10000, 20.0, 100.0)
        # 第二次回调间隔太短（<0.2s）速率算不出来 → 用 last_speed
        job = win.jobs[42]
        job['rate_dur'] = 1.0
        job['eta'] = win._compute_eta(job)
        win._refresh_task_row(42)
        txt = win.tbl_tasks.item(r, 5).text()
        ok('剩余时间有值', txt not in ('--', ''), txt)
        ok('剩余时间格式为 MM:SS 或含冒号', ':' in txt, txt)
        ok('速度列有值', win.tbl_tasks.item(r, 4).text() != '',
           win.tbl_tasks.item(r, 4).text())
        ok('大小列显示 已下/总量',
           '/' in win.tbl_tasks.item(r, 3).text(),
           win.tbl_tasks.item(r, 3).text())

        # 状态列显示阶段
        win._on_phase(42, '封装')
        ok('封装阶段状态列显示「封装中」',
           win.tbl_tasks.item(r, 2).text() == '封装中',
           win.tbl_tasks.item(r, 2).text())

        # ★ 完成后：剩余时间列显示「用时 …」
        win._update_task(42, '已完成', 'ok')
        txt = win.tbl_tasks.item(r, 5).text()
        ok('完成后显示「用时」', '用时' in txt, txt)
        # ★ 定时刷新不能把「用时」覆盖回「--」
        win.running_workers.add(42)
        win._tick_eta()
        txt2 = win.tbl_tasks.item(r, 5).text()
        ok('定时刷新不覆盖「用时」', '用时' in txt2, txt2)
        win.running_workers.discard(42)
    finally:
        win.close()


# ── 5. 暂停时冻结 ────────────────────────────────────────────
def test_pause_freezes_eta():
    print('\n[5] 暂停时剩余时间冻结')
    win = _make_win()
    try:
        le = win.lessons[0]
        win.jobs[7] = {'row': 0, 'lesson': le, 'camp': win.current_camp,
                       'out_path': os.path.join(OUT, 'y.mp4'),
                       'down': 0, 'total': 0, 'speed': 2.0,
                       'done_dur': 0.0, 'total_dur': 0.0, 'unit': 'dur',
                       'eta': 50.0, 'phase': '下载',
                       'meter': xqd_gui.SpeedMeter(),
                       'bmeter': xqd_gui.SpeedMeter(),
                       'rate_dur': 2.0,
                       'eta_fixed': 0.0, 't0': time.time()}
        win._add_task(le, win.current_camp, os.path.join(OUT, 'y.mp4'),
                      '下载中', 7)
        win.running_workers.add(7)

        win.control.pause()
        win._tick_eta()
        eta1 = win.jobs[7]['eta']
        ok('暂停后 ETA 保持不变', eta1 == 50.0, eta1)

        win.control.resume()
        win._tick_eta()
        ok('继续后 ETA 会重算（速率过期后为 None）',
           win.jobs[7]['eta'] is None, win.jobs[7]['eta'])
        win.running_workers.clear()
    finally:
        win.close()


# ── 6. 封装阶段估算 ──────────────────────────────────────────
def test_mux_estimate():
    print('\n[6] 封装阶段估算')
    win = _make_win()
    try:
        le = win.lessons[0]
        le.duration = 600
        job = {'lesson': le, 'total': 100 * 1024 * 1024,
               'phase': '下载', 'eta_fixed': 0.0}
        win._on_phase  # noqa
        win.jobs[99] = job
        win._on_phase(99, '封装')
        ok('封装阶段有估算值', job['eta_fixed'] > 0, job['eta_fixed'])
        eta, _ = win._job_eta(job)
        ok('封装阶段用 eta_fixed', eta == job['eta_fixed'], eta)
        # 10 MB/s 写 100MB = 10s，加 ffmpeg 600/60=10s，加 3s ≈ 23s
        ok('封装估算量级合理（10~40 秒）',
           10 <= job['eta_fixed'] <= 40, job['eta_fixed'])
    finally:
        win.close()


# ── 7. 全局汇总 ──────────────────────────────────────────────
def test_global_eta():
    print('\n[7] 全局剩余时间汇总')
    win = _make_win()
    try:
        le = win.lessons[0]
        le.duration = 100
        win.jobs[1] = {'row': 0, 'lesson': le, 'camp': win.current_camp,
                       'out_path': '', 'down': 0, 'total': 0, 'speed': 1.0,
                       'done_dur': 0.0, 'total_dur': 100.0, 'unit': 'dur',
                       'eta': 50.0, 'phase': '下载',
                       'meter': xqd_gui.SpeedMeter(),
                       'bmeter': xqd_gui.SpeedMeter(),
                       'rate_dur': 1.0,
                       'eta_fixed': 0.0, 't0': time.time()}
        win.running_workers.add(1)
        win._update_global_eta()
        txt = win.lbl_task_eta.text()
        ok('有汇总文字', '剩余约' in txt, txt)
        ok('显示在跑/排队数', '1 个在跑' in txt, txt)

        win.running_workers.clear()
        win.pending_queue = []
        win._update_global_eta()
        ok('空闲时清空汇总', win.lbl_task_eta.text() == '',
           win.lbl_task_eta.text())
    finally:
        win.close()


# ── 8. fmt 工具 ──────────────────────────────────────────────
def test_fmt():
    print('\n[8] 格式化函数')
    ok('秒 -> 只有秒（不显示分:）', xqd_gui.fmt_dur(45) == '45',
       xqd_gui.fmt_dur(45))
    ok('秒 -> 只有秒（不补零）', xqd_gui.fmt_dur(5) == '5',
       xqd_gui.fmt_dur(5))
    ok('分 -> M:SS（不显示时:）', xqd_gui.fmt_dur(90) == '1:30',
       xqd_gui.fmt_dur(90))
    ok('分 -> M:SS（秒补零）', xqd_gui.fmt_dur(125) == '2:05',
       xqd_gui.fmt_dur(125))
    ok('时 -> H:MM:SS（不显示天）', xqd_gui.fmt_dur(3661) == '1:01:01',
       xqd_gui.fmt_dur(3661))
    ok('天 -> D:HH:MM:SS', xqd_gui.fmt_dur(93784) == '1:02:03:04',
       xqd_gui.fmt_dur(93784))
    ok('0 -> 0', xqd_gui.fmt_dur(0) == '0', xqd_gui.fmt_dur(0))
    ok('负数 -> --', xqd_gui.fmt_dur(-1) == '--')
    ok('None -> --', xqd_gui.fmt_dur(None) == '--')
    ok('速度 KB/s', xqd_gui.fmt_speed(2048) == '2KB/s',
       xqd_gui.fmt_speed(2048))
    ok('速度 MB/s', xqd_gui.fmt_speed(5 * 1024 * 1024) == '5.0MB/s',
       xqd_gui.fmt_speed(5 * 1024 * 1024))
    ok('速度 0 -> --', xqd_gui.fmt_speed(0) == '--')


# ── 公共：造一个离屏窗口 ─────────────────────────────────────
class FakePlatform(xqd_platform.Platform):
    def __init__(self):
        xqd_platform.Platform.__init__(self, 'fake')
        self.camp = xqd_platform.Camp('测试营', 'camp-1', '正式营', 4)
        self.lessons = []
        for i in range(4):
            le = xqd_platform.Lesson(i, '第%d节课' % (i + 1),
                                      '2026.01.%02d' % (i + 1), 300)
            self.lessons.append(le)

    def list_camps(self, kind='正式营'):
        return [self.camp]

    def camp_catalog(self, camp):
        return list(self.lessons)

    def resolve(self, camp, lesson):
        return 'http://example.com/x.m3u8'


def _make_win():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = xqd_gui.MainWindow()
    win.ed_out.setText(OUT)
    win.out_dir = OUT
    win.cookie = 'fake=1'
    win.platform = FakePlatform()
    win.auto_check_auth = lambda: None
    win.current_camp = win.platform.camp
    win.camps = [win.platform.camp]
    win.load_lessons()
    app.processEvents()
    return win


def main():
    os.makedirs(OUT, exist_ok=True)
    tests = [test_speed_meter,
             test_eta_follows_speed_and_remaining,
             test_duration_ratio,
             test_table_columns,
             test_pause_freezes_eta,
             test_mux_estimate,
             test_global_eta,
             test_fmt]
    for t in tests:
        try:
            t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            FAIL.append(t.__name__ + ' 异常：%s' % e)

    print('\n' + '=' * 56)
    print('通过 %d，失败 %d' % (PASS[0], len(FAIL)))
    for f in FAIL:
        print('  失败：%s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
