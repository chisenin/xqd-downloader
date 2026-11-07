# -*- coding: utf-8 -*-
"""用**真实 GUI**跑完剩余全部课程下载 —— 端到端实测。

为什么不用 xqd_batch.py：用户明确要求「后续统一用 GUI 工具下载」，
而且要确认工具彻底没 BUG。所以这里驱动的是 xqd_gui.MainWindow 本体：
  授权 → 营列表 → 课表 → 勾选 → 下载选中 → 进度 → 任务表
走的全是 GUI 的代码路径，和用户手点完全一致。

与旧版的差别（2026-11-07 下午）：
  * 勾选不再依赖后台扫描的时机 —— 直接读 todo_live.json 白名单，
    按 stem 精确勾选要下的课。扫描仍会跑（GUI 自己会做），
    但决策不依赖它。
  * 失败的课会在本营结束后重试一轮（最多 2 轮）。
  * 分片临时目录落在 state/pdl_tmp（可用 XQD_TMP 环境变量改），
    下载完即清理，避免撑爆系统盘。

用法：
  python -u _lel/api/gui_full_run.py                # 全量
  python -u _lel/api/gui_full_run.py --limit 3      # 每个营只下前 3 节（试跑）
  python -u _lel/api/gui_full_run.py --camps "引气归源太极营"
  python -u _lel/api/gui_full_run.py --retry-rounds 2
"""
import argparse
import faulthandler
import json
import os
import tempfile
import sys
import time

# 崩溃时把 C 层栈打到 stderr（否则 Python 异常都看不到）
try:
    faulthandler.enable(file=sys.stderr, all_threads=True)
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_platform as P

OUT = os.environ.get('XQD_OUT', 'Z:/太极营')
TODO_JSON = os.path.join(ROOT, '_lel', 'api', 'todo_live.json')

STATE = {
    'phase': 'init',
    'camps': [],
    'camp_idx': 0,
    'kind_idx': 0,
    'kinds': [],
    'done': 0,
    'skip': 0,
    'failed': [],
    'retry_queue': [],
    'start': time.time(),
    'round': 0,
}


def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


def load_whitelist():
    """读 todo_live.json → {营名: set(stem)}，只要 status != 'ok' 的。"""
    wl = {}
    if not os.path.isfile(TODO_JSON):
        log('★ 找不到 %s，退化为「全选」（GUI 自己会跳过已存在）'
            % TODO_JSON)
        return wl
    data = json.load(open(TODO_JSON, encoding='utf-8'))
    for camp, blob in data.items():
        stems = set(r['stem'] for r in blob['rows']
                    if r.get('status') != 'ok')
        if stems:
            wl[camp] = stems
    log('白名单：%d 个营，共 %d 节待下载'
        % (len(wl), sum(len(v) for v in wl.values())))
    return wl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0,
                    help='每个营最多下几节（0 = 全部）')
    ap.add_argument('--camps', default='', help='只下这些营（逗号分隔）')
    ap.add_argument('--kinds', default='正式营,体验营')
    ap.add_argument('--quality', default='max')
    ap.add_argument('--dry', action='store_true', help='只跑流程不下内容')
    ap.add_argument('--cookie', default='',
                    help='直接指定 Cookie（跳过 MuMu 授权，用于隔离问题）')
    ap.add_argument('--retry-rounds', type=int, default=1,
                    help='失败课的额外重试轮数')
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    if args.cookie:
        # 隔离用：彻底关掉自动授权（MainWindow.__init__ 里排的
        # QTimer.singleShot(300, self.auto_check_auth) 也会被拦掉）
        xqd_gui.MainWindow.auto_check_auth = lambda self: None

    win = xqd_gui.MainWindow()
    win.resize(1280, 860)
    win.show()

    win.out_dir = OUT
    win.ed_out.setText(OUT)
    idx = win.cmb_quality.findData(args.quality)
    if idx >= 0:
        win.cmb_quality.setCurrentIndex(idx)

    STATE['kinds'] = [k for k in args.kinds.split(',') if k]
    STATE['want_camps'] = [c for c in args.camps.split(',') if c]
    STATE['args'] = args
    STATE['wl'] = load_whitelist()

    # 统计成功/失败（挂在 GUI 的真实回调上）
    _ok = win._on_download_ok
    _fail = win._on_download_failed

    def on_ok(job_id, msg, out_path):
        STATE['done'] += 1
        _ok(job_id, msg, out_path)

    def on_fail(job_id, msg):
        job = win.jobs.get(job_id) or {}
        le = job.get('lesson')
        camp = job.get('camp')
        cname = getattr(camp, 'name', '?')
        title = getattr(le, 'title', '?')
        STATE['failed'].append((cname, title, msg))
        STATE['retry_queue'].append((cname, title, msg))
        _fail(job_id, msg)

    win._on_download_ok = on_ok
    win._on_download_failed = on_fail

    # 把 GUI 内部日志同步到 stdout（否则只有界面里能看到）
    _glog = win.log

    def glog(text):
        print('    | %s' % text, flush=True)
        _glog(text)

    win.log = glog

    # 捕获未处理异常，免得进程直接死掉看不出原因
    def on_exc(exc_type, exc, tb):
        import traceback
        log('★ 未捕获异常：%s' % exc_type.__name__)
        traceback.print_exception(exc_type, exc, tb)
        sys.stdout.flush()

    sys.excepthook = on_exc

    if args.cookie:
        # 跳过 MuMu 授权（隔离用）
        win.cookie = args.cookie
        win.platform.cookie = args.cookie
        log('使用指定的 Cookie，跳过 MuMu 授权')
    else:
        win.auto_check_auth()

    timer = QTimer()
    timer.timeout.connect(lambda: tick(win, args))
    timer.start(1000)

    def on_quit():
        log('=' * 50)
        log('总用时 %.1f 分钟' % ((time.time() - STATE['start']) / 60.0))
        log('完成 %d 节，跳过 %d 节，失败 %d 节'
            % (STATE['done'], STATE['skip'], len(STATE['failed'])))
        if STATE['failed']:
            log('失败清单：')
            for camp, title, msg in STATE['failed']:
                log('  [%s] %s —— %s' % (camp, title, msg))
        app.quit()

    win._full_run_quit = on_quit
    return app.exec()


def pick_rows(win, camp_name, limit=0):
    """按白名单勾选该营要下的课；返回 (勾选数, 需要的 stem 集合)。"""
    wl = STATE.get('wl') or {}
    want = wl.get(camp_name)
    n = 0
    for r in range(win.tbl_lessons.rowCount()):
        item = win.tbl_lessons.item(r, 0)
        if not item:
            continue
        le = win.lesson_of_row.get(r)
        if not le:
            continue
        stem = P.lesson_stem(le)
        # 白名单为空 → 全选（GUI 自己会跳过已存在的）
        hit = True if not want else (stem in want)
        if hit and limit and n >= limit:
            hit = False
        item.setCheckState(Qt.Checked if hit else Qt.Unchecked)
        if hit:
            n += 1
    return n


def tick(win, args):
    phase = STATE['phase']

    # ── 等授权 ──
    if phase == 'init':
        if not win.cookie:
            # 授权最长等 6 分钟（MuMu 启动 + 用户可能需要登录）
            if time.time() - STATE['start'] > 360:
                log('★ 授权超时（6 分钟），中止')
                QTimer.singleShot(300, win._full_run_quit)
            return
        STATE['phase'] = 'load_camps'
        log('授权已就绪，开始加载营列表')
        return

    # ── 加载营列表（逐个 kind）──
    if phase == 'load_camps':
        if STATE['kind_idx'] >= len(STATE['kinds']):
            if not STATE['camps']:
                log('★ 没有找到任何营')
                QTimer.singleShot(300, win._full_run_quit)
                return
            STATE['camp_idx'] = 0
            STATE['phase'] = 'camp'
            log('共 %d 个营待处理' % len(STATE['camps']))
            return

        kind = STATE['kinds'][STATE['kind_idx']]
        win.cmb_kind.setCurrentText(kind)
        win.load_camps()
        # 营列表此时只含当前 kind 的营 —— 必须在这里就切营，
        # 等到后面再切会找不到（列表已被后一个 kind 覆盖）
        for c in list(win.camps):
            if STATE['want_camps'] and c.name not in STATE['want_camps']:
                continue
            STATE['camps'].append(c)
        log('%s：%d 个营（累计 %d）'
            % (kind, len(win.camps), len(STATE['camps'])))
        STATE['kind_idx'] += 1
        return

    # ── 切到下一个营 ──
    if phase == 'camp':
        if STATE['camp_idx'] >= len(STATE['camps']):
            if STATE['round'] < args.retry_rounds and STATE['retry_queue']:
                # 进入重试轮：只保留失败过的营
                retry_camps = []
                for cname, _t, _m in STATE['retry_queue']:
                    if cname not in [c.name for c in retry_camps]:
                        for c in STATE['camps']:
                            if c.name == cname:
                                retry_camps.append(c)
                                break
                STATE['retry_queue'] = []
                if retry_camps:
                    STATE['round'] += 1
                    STATE['camps'] = retry_camps
                    STATE['camp_idx'] = 0
                    log('★ 进入重试第 %d 轮：%d 个营'
                        % (STATE['round'], len(retry_camps)))
                    return
            STATE['phase'] = 'done'
            log('全部营处理完毕')
            QTimer.singleShot(500, win._full_run_quit)
            return

        camp = STATE['camps'][STATE['camp_idx']]
        log('')
        log('—— 营 %d/%d：%s ——'
            % (STATE['camp_idx'] + 1, len(STATE['camps']), camp.name))

        # 营列表可能已被后一个 kind 覆盖 → 先切回该营所属的 kind
        if win.cmb_kind.currentText() != camp.kind:
            win.cmb_kind.setCurrentText(camp.kind)
            win.load_camps()

        # 走 GUI 真实的营选择路径
        found = False
        for i in range(win.lst_camps.count()):
            it = win.lst_camps.item(i)
            if it.text().startswith(camp.name):
                win.lst_camps.setCurrentRow(i)
                found = True
                break
        if not found:
            log('★ 营列表里找不到「%s」，跳过' % camp.name)
            STATE['camp_idx'] += 1
            return
        STATE['phase'] = 'load'
        return

    # ── 课表加载完 → 勾选 → 开始下载 ──
    if phase == 'load':
        if not win.lessons:
            return
        cur = STATE['camps'][STATE['camp_idx']]
        if win.current_camp is None or win.current_camp.name != cur.name:
            return

        log('课表 %d 节' % len(win.lessons))
        # 等后台扫描（已下载检测）跑完，否则会重复下载
        t0 = time.time()
        while win.scan_worker and win.scan_worker.isRunning() \
                and time.time() - t0 < 300:
            QApplication.processEvents()
            time.sleep(0.2)

        # ★ 按白名单精确勾选（不依赖扫描时机）
        n = pick_rows(win, cur.name, args.limit)
        log('待下载 %d 节（已存在的会被 GUI 自动跳过）' % n)
        if n == 0:
            STATE['camp_idx'] += 1
            STATE['phase'] = 'camp'
            return

        STATE['before'] = (STATE['done'], STATE['skip'])
        STATE['camp_start'] = time.time()
        win.start_download_selected()
        STATE['phase'] = 'download'
        return

    # ── 下载中 ──
    if phase == 'download':
        running = len(win.running_workers)
        queued = len(win.pending_queue)
        if running == 0 and queued == 0:
            el = (time.time() - STATE.get('camp_start', time.time())) / 60.0
            log('营完成，用时 %.1f 分钟' % el)
            STATE['camp_idx'] += 1
            STATE['phase'] = 'camp'
        return


if __name__ == '__main__':
    sys.exit(main())
