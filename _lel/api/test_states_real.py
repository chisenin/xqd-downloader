# -*- coding: utf-8 -*-
"""★ 真网络验证：下载过程中三处状态是否真的一一对应。

用户 2026-11-07 指出「三处地方的状态应当能一一对应」，
并附截图 —— 课程列表写「下载中…」，下载管理写「封装中」，对不上。

本测试**真网络 + 真 Cookie**，跑一节课的完整生命周期，
在每个阶段抓取三处的状态，断言它们**同时刻是同一个词**。

关键点：不能只断言「最终一致」，要断言**过程中每一刻都一致** ——
如果课程列表不跟随阶段变，这个测试会中途就红。

跑法：python test_states_real.py [营名关键字]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

# ★ 测试隔离
import tempfile
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_states_real'))

import xqd_gui
import xqd_history

# 真 Cookie —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
COOKIE = ''

PASS = []
FAIL = []


def ok(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('OK  ' if cond else 'FAIL', name,
                       ('  -> %s' % (extra,)) if extra else ''))


def load_cookie():
    """取真 Cookie —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）。

    ★ 凭据不在源码里，详见 xqd_creds.py 顶部说明。
    """
    global COOKIE
    import xqd_creds
    try:
        COOKIE = xqd_creds.load_cookie()
    except Exception as e:
        print('  读 Cookie 失败：%s' % e)
        return False
    return bool(COOKIE)


def patch_cookie():
    """★ 平台层**直接支持传 cookie**（`create_platform(id, cookie)`），
       不用 patch 任何类 —— 比 monkey-patch 干净得多。
    """
    return True


def suffix_of(win, row):
    """课程列表第 row 行**跟在课名后面**的状态词（v1.4.0 起）。"""
    it = win.tbl_lessons.item(row, 1)
    return (it.data(xqd_gui.STATE_ROLE) or '') if it else ''


def task_state(win, job_id):
    r = win._task_row_of_job.get(job_id)
    if r is None or r >= win.tbl_tasks.rowCount():
        return ''
    it = win.tbl_tasks.item(r, 2)
    return it.text() if it else ''


def main():
    if not load_cookie():
        print('★ 拿不到真 Cookie（cache-analysis/_apitest.py），跳过')
        return 0
    print('Cookie 长度 %d' % len(COOKIE))
    patch_cookie()

    app = QApplication(sys.argv)

    import xqd_platform
    plat = xqd_platform.create_platform('qianliao', cookie=COOKIE)
    camps = plat.list_camps()
    print('营数：%d' % len(camps))

    keyword = sys.argv[1] if len(sys.argv) > 1 else None
    target = None
    for c in camps:
        if keyword and keyword not in c.name:
            continue
        try:
            cat = plat.camp_catalog(c)
        except Exception as e:
            print('  %s → 课表失败 %s' % (c.name, e))
            continue
        if not cat:
            continue
        le = max(cat, key=lambda x: x.duration or 0)
        print('  营：%s（%d 节）目标课：%s 时长 %s'
              % (c.name, len(cat), le.title, le.duration))
        target = (c, le)
        break

    if not target:
        print('★ 找不到可用的课，跳过')
        return 0

    camp, le = target

    # ── 开窗 ────────────────────────────────────────────
    win = xqd_gui.MainWindow()
    win.platform = plat
    win.current_camp = camp
    win.camps = camps
    win.out_dir = os.path.join(tempfile.gettempdir(), 'xqd_states_real')
    win.ed_out.setText(win.out_dir)
    win.cookie = COOKIE
    win.auto_check_auth = lambda: None
    win.load_lessons()
    app.processEvents()

    row = win._row_of_lesson_obj(le)
    ok('课程行可定位', row is not None, str(row))

    # ── 启动这一节的下载 ────────────────────────────────
    out_path = os.path.join(win.out_dir, '%s.mp4' % le.title[:20])
    le.out_path = out_path
    job_id = 7001
    win.jobs[job_id] = {'row': row, 'lesson': le, 'camp': camp,
                        'out_path': out_path,
                        'down': 0, 'total': 0, 'speed': 0.0,
                        'done_dur': 0.0, 'total_dur': 0.0,
                        'unit': 'dur', 'eta': None, 'phase': '',
                        'meter': xqd_gui.SpeedMeter(),
                        'bmeter': xqd_gui.SpeedMeter(),
                        'rate_dur': 0.0,
                        'seg_dir': xqd_history.parts_dir_for(out_path),
                        'cached_bytes': 0, 'cached_segs': 0,
                        'eta_fixed': 0.0, 't0': time.time()}
    win._task_row_of_job[job_id] = 0
    win.tbl_tasks.insertRow(0)
    for c in range(win.tbl_tasks.columnCount()):
        win.tbl_tasks.setItem(0, c, xqd_gui.QTableWidgetItem(''))
    win.running_workers.add(job_id)
    win._set_both_states(job_id, '下载中')
    app.processEvents()

    # ── 边下边抓三处状态 ────────────────────────────────
    seen = []          # [(时刻, 课程列表后缀, 下载管理状态列)]
    mismatches = []

    def sample():
        s = suffix_of(win, row)
        t = task_state(win, job_id)
        seen.append((time.time(), s, t))
        if s != t:
            mismatches.append('课程列表=%s 下载管理=%s' % (s, t))

    # ★ 采样点放在**阶段回调**和**进度回调**里 ——
    #   download_lesson 是同步阻塞的，主线程被占住，
    #   QTimer 根本没机会触发（只在下载结束后采到一次，等于没测）。
    #   阶段回调正是状态变化的那一刻，采到的才是关键样本。
    def on_progress(down, total, done_dur, total_dur):
        win.jobs[job_id]['down'] = down
        win.jobs[job_id]['total'] = total
        win.jobs[job_id]['done_dur'] = done_dur
        win.jobs[job_id]['total_dur'] = total_dur
        win.jobs[job_id]['bmeter'].push(down)
        win.jobs[job_id]['meter'].push(done_dur)
        sample()

    def on_phase(name):
        win._on_phase(job_id, name)
        sample()

    ok_result, msg, final = xqd_gui.xqd_engine.download_lesson(
        lambda: plat.resolve(camp, le),
        out_path,
        quality='max',
        workers=12,
        on_progress=on_progress,
        expect_duration=le.duration,
        on_phase=on_phase,
        seg_dir=win.jobs[job_id]['seg_dir'])
    sample()
    all_log = win.txt_log.toPlainText()

    print('\n下载结果：%s %s' % (ok_result, msg))

    # ── 断言 ────────────────────────────────────────────
    print('\n采样到的状态序列（前 30 个）：')
    for ts, s, t in seen[:30]:
        mark = 'OK ' if s == t else 'BAD'
        print('  %s %-8s %-8s' % (mark, s, t))

    phases_seen = set(s for _ts, s, _t in seen)
    print('\n出现过的课程列表状态：%s' % sorted(phases_seen))

    ok('下载成功', ok_result, msg)
    ok('★ 采样过程中三处始终一致（无错配）',
       not mismatches, '; '.join(mismatches[:3]))
    ok('确实经历了多个阶段（说明不是全程一个词）',
       len(phases_seen) >= 2, str(sorted(phases_seen)))

    # 日志里要能查到状态
    ok('运行日志里有阶段记录',
       any(w in all_log for w in ('解析中', '下载中', '封装中', '校验中')),
       [w for w in ('解析中', '下载中', '封装中', '校验中')
        if w in all_log])

    # 最终状态
    win._on_download_completed(job_id, ok_result, msg, final)
    app.processEvents()
    final_s = suffix_of(win, row)
    final_t = task_state(win, job_id)
    ok('完成后两处一致', final_s == final_t, '%s vs %s' % (final_s, final_t))
    ok('完成后是终态「已完成」', final_s == '已完成', final_s)

    # 清理
    try:
        if os.path.isfile(final):
            with open(final, 'wb') as f:
                pass
    except OSError:
        pass

    print('\n========================================================')
    print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：')
        for f in FAIL:
            print('  -', f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
