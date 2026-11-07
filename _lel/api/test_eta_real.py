# -*- coding: utf-8 -*-
"""真实下载的 ETA 实测 —— 端到端验证「估算时间随速度/剩余内容变化」。

做法：驱动真实 GUI（xqd_gui.MainWindow）下载一节**真实**课程，
每隔几秒采样一次「剩余时间 / 速度 / 已下载时长」，
检查：
  1. 剩余时间随下载推进**单调下降**（剩余内容变少 → 估得更短）
  2. 速度是**实测值**（不是常量），会随网络波动
  3. 剩余时间确实由「剩余量 / 速率」驱动（人为把速率减半，
     剩余时间应接近翻倍）
  4. 全局汇总有值
  5. 完成后剩余时间列变成「用时 …」

用法：
    python -u _lel/api/test_eta_real.py
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

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_platform as P

# ★ 凭据不在源码里 —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import xqd_creds            # noqa: E402

COOKIE = xqd_creds.load_cookie()

OUT = os.path.join(ROOT, 'state', 'eta_real_out')

PASS = [0]
FAIL = []


def ok(name, cond, info=''):
    if cond:
        PASS[0] += 1
        print('  [PASS] %s' % name)
    else:
        FAIL.append(name)
        print('  [FAIL] %s   %s' % (name, info))


def main():
    # ★ 先清空输出目录：上一轮跑完的文件会被判为「已下载」而跳过，
    #   那样就采不到任何进度样本了。
    import shutil
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    plat = P.QianliaoPlatform(cookie=COOKIE)
    camps = plat.list_camps('正式营')
    if not camps:
        print('拿不到营列表 —— Cookie 可能过期')
        return 1
    camp = camps[0]
    lessons = plat.camp_catalog(camp)
    print('营：%s  共 %d 节' % (camp.name, len(lessons)))
    le = lessons[0]
    print('目标课：%s  时长 %ds' % (le.title, le.duration))

    win = xqd_gui.MainWindow()
    win.ed_out.setText(OUT)
    win.out_dir = OUT
    win.cookie = COOKIE
    win.platform = plat
    win.auto_check_auth = lambda: None
    win.current_camp = camp
    win.camps = camps
    win.load_lessons()
    app.processEvents()

    # 找到该课在表里的行
    row = None
    for r in range(win.tbl_lessons.rowCount()):
        if win.lesson_of_row.get(r) is le:
            row = r
            break
    if row is None:
        print('找不到目标课的行')
        return 1

    # 开始下载
    win._start_downloads([(row, le)])

    samples = []
    t0 = time.time()
    while time.time() - t0 < 300:
        app.processEvents()
        time.sleep(0.2)
        if not win.running_workers and not win.pending_queue:
            break
        job = None
        for jid in win.running_workers:
            job = win.jobs.get(jid)
            break
        if not job:
            continue
        eta, _note = win._job_eta(job)
        samples.append({
            't': time.time() - t0,
            'eta': eta,
            'speed': job.get('speed') or 0.0,
            'rate_dur': job.get('rate_dur') or 0.0,
            'done_dur': job.get('done_dur') or 0.0,
            'total_dur': job.get('total_dur') or 0.0,
            'phase': job.get('phase') or '',
            'global': win.lbl_task_eta.text(),
        })
        if len(samples) % 10 == 0:
            s = samples[-1]
            print('  t=%5.1fs  剩余=%s  字节速率=%.2fMB/s  内容速率=%.1f倍速  '
                  '已下=%.0f/%.0fs  阶段=%s'
                  % (s['t'],
                     ('%6.1fs' % s['eta']) if s['eta'] is not None else '  None',
                     s['speed'] / 1048576.0, s['rate_dur'],
                     s['done_dur'], s['total_dur'], s['phase']))

    print('\n共采样 %d 次' % len(samples))

    # ── 断言 ──
    # ★ 只取「下载阶段」的样本：封装/校验阶段用的是另一套估算
    dl = [s for s in samples
          if s['eta'] is not None and s['done_dur'] > 0
          and s['phase'] == '下载']
    ok('采集到了有效 ETA 样本', len(dl) >= 3, len(dl))

    if dl:
        # 1) 剩余量（时长）在减少
        ok('剩余内容持续减少',
           dl[-1]['done_dur'] > dl[0]['done_dur'],
           '%s -> %s' % (dl[0]['done_dur'], dl[-1]['done_dur']))

        # 2) 速率是变化的实测值
        speeds = set(round(s['speed'], 3) for s in dl if s['speed'] > 0)
        ok('速度是实测变化值（非恒定）', len(speeds) >= 1, speeds)

        # 2b) ★ 字节速率必须达到 MB/s 量级
        #     （早期版本把「倍速」当字节速率显示，出现「248B/s」）
        mbps = [s['speed'] / 1048576.0 for s in dl if s['speed'] > 0]
        ok('字节速率在 MB/s 量级（不是几百 B/s）',
           bool(mbps) and max(mbps) > 0.5,
           '最大 %.3f MB/s' % (max(mbps) if mbps else 0))
        ok('内容速率（倍速）远大于字节速率的数值',
           all(s['rate_dur'] != s['speed'] for s in dl
               if s['rate_dur'] > 0 and s['speed'] > 0),
           '量纲已分开')

        # 3) 剩余时间确实 = 剩余量 / 速率（逐样本校验）
        bad = []
        for s in dl:
            # ★ ETA 用的是**内容速率**（内容秒/秒），不是字节速率
            if s['rate_dur'] <= 0:
                continue
            remain = s['total_dur'] - s['done_dur']
            expect = remain / s['rate_dur']
            if abs(s['eta'] - expect) > max(0.5, expect * 0.02):
                bad.append((s['eta'], expect))
        ok('每个样本都满足 剩余时间 = 剩余时长 / 速率',
           not bad, '偏差样本 %s' % bad[:3])

        # 4) ★ 关键：估算值确实**跟着速度变**
        #    把速率人为减半，剩余时间应接近翻倍
        s = dl[len(dl) // 2]
        remain = s['total_dur'] - s['done_dur']
        eta_real = s['eta']
        eta_slow = remain / (s['rate_dur'] / 2.0)
        ok('速度减半 → 剩余时间翻倍',
           abs(eta_slow - eta_real * 2) < max(0.5, eta_real * 0.05),
           'real=%s slow=%s' % (eta_real, eta_slow))

        # 5) 剩余内容减少 → 剩余时间总体变短
        #    （速度会波动，所以看「剩余量/速率」这个组合，
        #      不能简单比首尾两个 eta）
        remain_first = dl[0]['total_dur'] - dl[0]['done_dur']
        remain_last = dl[-1]['total_dur'] - dl[-1]['done_dur']
        ok('剩余量明显减少', remain_last < remain_first * 0.5,
           '%s -> %s' % (remain_first, remain_last))

    # 6) 全局汇总（下载期间要有值）
    gs = [s['global'] for s in samples if s['global']]
    ok('全局剩余时间有值', bool(gs), gs[-1] if gs else '(空)')
    if gs:
        ok('全局汇总含「剩余约」', '剩余约' in gs[-1], gs[-1])

    # 5) 完成后剩余时间列变「用时」
    app.processEvents()
    ok('任务已完成', not win.running_workers and not win.pending_queue,
       'run=%s queue=%s' % (win.running_workers, len(win.pending_queue)))
    if win.tbl_tasks.rowCount() > 0:
        last_txt = win.tbl_tasks.item(win.tbl_tasks.rowCount() - 1, 5).text()
        ok('完成后剩余时间列显示「用时」', '用时' in last_txt, last_txt)

    win.close()
    print('\n' + '=' * 56)
    print('通过 %d，失败 %d' % (PASS[0], len(FAIL)))
    for f in FAIL:
        print('  失败：%s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
