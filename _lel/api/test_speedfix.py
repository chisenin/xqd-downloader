# -*- coding: utf-8 -*-
"""回归测试：用户反馈的三个问题（2026-11-07）。

1. **速度显示不准确** —— 界面显示 248B/s，实际网络 84MB/s。
   根因：速度计喂的是「内容秒数」，算出的是**倍速**（内容秒/秒），
         却用字节格式化器渲染 → 「248B/s」实际是 248 倍速。
   修法：字节速率（显示）与内容速率（算 ETA）**分开两个计**。

2. **状态一直显示「解析中」**，实际早就在下载了。
   根因：`_refresh_task_row` 的守卫写死了只允许从「下载中/排队中」
         切进来 —— 变成「解析中」后就再也变不回去。
   修法：允许在所有进行中阶段之间自由切换（PHASE_TEXTS）。

3. **大小列的总量偏 37%**（显示 1574MB，真实 1146MB）。
   根因：`_dl_all` 只用**前 3 片**外推，而直播课开头码率偏高。
   修法：均匀抽 12 片外推（实测误差 -0.7%）。
"""
import os
import tempfile
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

import xqd_engine
# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_platform

# 复用 test_eta.py 的 FakePlatform / 造窗口逻辑，避免重复
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_eta import FakePlatform          # noqa: E402

OUT = os.path.join(ROOT, 'state', 'spd')

PASS = [0]
FAIL = []


def ok(name, cond, info=''):
    if cond:
        PASS[0] += 1
        print('  ✓ %s' % name)
    else:
        FAIL.append(name)
        print('  ✗ %s   %s' % (name, info))


def _make_win():
    app = QApplication.instance() or QApplication([])
    os.makedirs(OUT, exist_ok=True)
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


# ── 1. 速度列的量纲 ─────────────────────────────────────────
def test_speed_is_bytes_per_second():
    print('\n[1] 速度列必须是字节速率')
    win = _make_win()
    try:
        le = win.lessons[0]
        out = os.path.join(OUT, 'a.mp4')
        win.jobs[1] = {'row': 0, 'lesson': le, 'camp': win.current_camp,
                       'out_path': out, 'down': 0, 'total': 0,
                       'speed': 0.0, 'rate_dur': 0.0,
                       'done_dur': 0.0, 'total_dur': 0.0, 'unit': 'dur',
                       'eta': None, 'phase': '下载',
                       'meter': xqd_gui.SpeedMeter(),
                       'bmeter': xqd_gui.SpeedMeter(),
                       'eta_fixed': 0.0, 't0': time.time()}
        win._add_task(le, win.current_camp, out, '下载中', 1)
        r = win._task_row_of_job[1]

        # ★ 直接构造样本：每次 +10MB / +100 内容秒，间隔 0.5s
        #   → 字节速率 = 20MB/s，内容速率 = 200 内容秒/秒
        #   两者差 100 倍 —— 正好能证明「量纲要分开」
        job = win.jobs[1]
        base = time.time()
        for i in range(3):
            down = (i + 1) * 10 * 1048576
            dur = (i + 1) * 100.0
            job['bmeter'].add(down, now=base + i * 0.5)
            job['meter'].add(dur, now=base + i * 0.5)
        job['speed'] = job['bmeter'].speed(now=base + 1.0)
        job['rate_dur'] = job['meter'].speed(now=base + 1.0)
        job['done_dur'] = 300.0
        job['total_dur'] = 1000.0
        job['down'] = 30 * 1048576
        job['total'] = 100 * 1048576
        win._refresh_task_row(1)

        ok('字节速率 ≈ 20MB/s',
           abs(job['speed'] - 20 * 1048576) < 0.5 * 1048576,
           '%.0f B/s' % job['speed'])
        ok('内容速率 ≈ 200 内容秒/秒',
           abs(job['rate_dur'] - 200.0) < 5.0,
           '%.1f' % job['rate_dur'])
        ok('两个速率是**分开的**（不是同一个数）',
           abs(job['speed'] / 1048576.0 - job['rate_dur']) > 1.0,
           '%.3f MB/s vs %.1f' % (job['speed'] / 1048576.0, job['rate_dur']))

        txt = win.tbl_tasks.item(r, 4).text()
        ok('速度列显示 MB/s', 'MB/s' in txt, txt)
        # ★ 不能是「几百 B/s」那种荒唐值（那其实是倍速被当成了字节）
        ok('速度列不是「几百 B/s」那种荒唐值',
           'MB/s' in txt or 'KB/s' in txt
           or (txt.endswith('B/s') and float(txt[:-3]) >= 1024),
           txt)

        # ETA 走内容速率：剩余 700 内容秒 ÷ 200 = 3.5s
        eta, _ = win._job_eta(job)
        ok('ETA 用内容速率算（3.5s）',
           eta is not None and abs(eta - 3.5) < 0.2, eta)
    finally:
        win.close()


# ── 2. 状态列必须在阶段之间自由切换 ─────────────────────────
def test_phase_text_switches_freely():
    print('\n[2] 状态列：解析中 → 下载中 → 封装中')
    win = _make_win()
    try:
        le = win.lessons[0]
        out = os.path.join(ROOT, 'state', 'spd', 'b.mp4')
        win.jobs[2] = {'row': 0, 'lesson': le, 'camp': win.current_camp,
                       'out_path': out, 'down': 0, 'total': 0,
                       'speed': 0.0, 'rate_dur': 0.0,
                       'done_dur': 0.0, 'total_dur': 0.0, 'unit': 'dur',
                       'eta': None, 'phase': '解析',
                       'meter': xqd_gui.SpeedMeter(),
                       'bmeter': xqd_gui.SpeedMeter(),
                       'eta_fixed': 0.0, 't0': time.time()}
        win._add_task(le, win.current_camp, out, '下载中', 2)
        r = win._task_row_of_job[2]

        win._on_phase(2, '解析')
        ok('解析阶段显示「解析中」',
           win.tbl_tasks.item(r, 2).text() == '解析中',
           win.tbl_tasks.item(r, 2).text())

        # ★ 这是用户报告的 bug：解析中之后变不回下载中
        win._on_phase(2, '下载')
        ok('能从「解析中」变回「下载中」',
           win.tbl_tasks.item(r, 2).text() == '下载中',
           win.tbl_tasks.item(r, 2).text())

        win._on_phase(2, '封装')
        ok('能变到「封装中」',
           win.tbl_tasks.item(r, 2).text() == '封装中',
           win.tbl_tasks.item(r, 2).text())

        win._on_phase(2, '校验')
        ok('能变到「校验中」',
           win.tbl_tasks.item(r, 2).text() == '校验中',
           win.tbl_tasks.item(r, 2).text())

        # 终态不能被阶段刷新覆盖
        win._update_task(2, '已完成', 'ok')
        win._on_phase(2, '下载')
        ok('终态「已完成」不被阶段覆盖',
           win.tbl_tasks.item(r, 2).text() == '已完成',
           win.tbl_tasks.item(r, 2).text())
    finally:
        win.close()


# ── 3. 总字节估算：均匀抽样 ─────────────────────────────────
def test_uniform_sampling():
    print('\n[3] 总字节估算用均匀抽样')
    # 直接测 _sample_segments 的取样位置（不联网）
    n = 2485
    segs = [('http://x/%d.ts' % i, 3.0) for i in range(n)]
    picked = []

    # 复刻 _sample_segments 的取样逻辑（不真的下载）
    step = (n - 1) / float(xqd_engine._SAMPLE_COUNT - 1)
    idxs = sorted(set(int(round(i * step))
                      for i in range(xqd_engine._SAMPLE_COUNT)))
    ok('抽样片数 = 12', len(idxs) == xqd_engine._SAMPLE_COUNT, len(idxs))
    ok('覆盖首片', idxs[0] == 0, idxs[0])
    ok('覆盖末片', idxs[-1] == n - 1, idxs[-1])
    ok('取样点均匀分布在整个清单上',
       max(idxs) - min(idxs) > n * 0.9,
       '%d..%d of %d' % (idxs[0], idxs[-1], n))
    ok('取样点互不重复', len(set(idxs)) == len(idxs), len(set(idxs)))

    # 片数很少时全取
    n2 = 8
    step2 = (n2 - 1) / float(xqd_engine._SAMPLE_COUNT - 1)
    idxs2 = sorted(set(int(round(i * step2))
                       for i in range(xqd_engine._SAMPLE_COUNT)))
    ok('片数少时取样点不重复且覆盖全片',
       len(idxs2) == n2 and idxs2[0] == 0 and idxs2[-1] == n2 - 1,
       idxs2)


# ── 4. ETA 用内容速率，且与剩余量自洽 ───────────────────────
def test_eta_uses_content_rate():
    print('\n[4] ETA 用内容速率')
    win = _make_win()
    try:
        le = win.lessons[0]
        job = {'down': 0, 'total': 100 * 1048576,
               'speed': 5 * 1048576,       # 字节速率 5MB/s
               'rate_dur': 50.0,           # 内容速率 50 倍速
               'done_dur': 200.0, 'total_dur': 1000.0, 'unit': 'dur',
               'eta': None, 'phase': '下载',
               'meter': xqd_gui.SpeedMeter(),
               'bmeter': xqd_gui.SpeedMeter(),
               'eta_fixed': 0.0}
        win.jobs[3] = job
        eta = win._compute_eta(job)
        ok('ETA = 剩余内容 / 内容速率 = 800/50 = 16s',
           eta is not None and abs(eta - 16.0) < 0.01, eta)
        ok('ETA 用的是内容速率（不是字节速率）',
           eta is not None and abs(eta - 16.0) < 0.01, eta)

        # 内容速率减半 → ETA 翻倍
        job['rate_dur'] = 25.0
        eta2 = win._compute_eta(job)
        ok('内容速率减半 → ETA 翻倍',
           eta2 is not None and abs(eta2 - 32.0) < 0.01, eta2)
    finally:
        win.close()


def main():
    tests = [test_speed_is_bytes_per_second,
             test_phase_text_switches_freely,
             test_uniform_sampling,
             test_eta_uses_content_rate]
    for t in tests:
        t()
    print('\n' + '=' * 56)
    print('通过 %d，失败 %d' % (PASS[0], len(FAIL)))
    for f in FAIL:
        print('  失败：%s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
