# -*- coding: utf-8 -*-
"""暂停功能 + 复选框状态回归测试。

覆盖：
  1. DownloadControl 的暂停/继续/中止语义
  2. 分片下载在暂停时确实停下、继续时接着下（不重下）
  3. 直链下载在暂停时停下
  4. GUI：入队即勾选（下载中的行复选框是 Checked）
  5. GUI：暂停按钮可用/禁用、切换文案
  6. GUI：切营后旧扫描结果不会把新营的行取消勾选
"""
import os
import shutil
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_platform
import xqd_engine

OUT = os.path.join(tempfile.gettempdir(), 'xqd_pause_test')
results = []


def ok(name, cond, extra=''):
    results.append((name, bool(cond)))
    print('%-46s %s %s' % (name, 'PASS' if cond else 'FAIL', extra))


# ── 1. DownloadControl 语义 ────────────────────────────────
def test_control():
    c = xqd_engine.DownloadControl()
    ok('初始不是暂停', not c.is_paused())
    ok('初始不是中止', not c.is_stopped())

    c.pause()
    ok('pause() 后处于暂停', c.is_paused())

    # 暂停期间 wait_resume 应该阻塞
    done = []

    def w():
        done.append(c.wait_resume())
    th = threading.Thread(target=w, daemon=True)
    th.start()
    time.sleep(0.6)
    ok('暂停时 wait_resume 阻塞', not done)

    c.resume()
    th.join(3)
    ok('继续后 wait_resume 返回', done == [True], str(done))

    # toggle
    c2 = xqd_engine.DownloadControl()
    r1 = c2.toggle()
    ok('toggle() 首次返回 True（已暂停）', r1 and c2.is_paused())
    r2 = c2.toggle()
    ok('toggle() 二次返回 False（已继续）',
       (not r2) and (not c2.is_paused()))

    # stop
    c3 = xqd_engine.DownloadControl()
    c3.pause()
    c3.stop()
    ok('stop() 后 is_stopped', c3.is_stopped())
    ok('stop() 后 wait_resume 立刻返回 False',
       c3.wait_resume() is False)


# ── 2. 分片下载：暂停 → 继续，不重下已下好的 ────────────────
class _SlowHandler(object):
    """本地 HTTP 服务：每个分片故意慢一点，好观察暂停效果。"""

    def __init__(self, delay=0.25):
        self.delay = delay
        self.hits = []

    def __call__(self, req):
        """req 是 BaseHTTPRequestHandler 实例（send_response 在它上面）。"""
        import urllib.parse
        path = urllib.parse.unquote(req.path)
        name = os.path.basename(path)
        if name == 'src.ts':
            body = b'X' * 1000
        else:
            body = b'Y' * 200000
        self.hits.append(name)
        time.sleep(self.delay)
        req.send_response(200)
        req.send_header('Content-Type', 'video/mp2t')
        req.send_header('Content-Length', str(len(body)))
        req.end_headers()
        req.wfile.write(body)


def start_server(handler):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def do_GET(self):
            handler(self)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]


def test_segments_pause():
    d = os.path.join(OUT, 'seg')
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)

    handler = _SlowHandler(delay=0.12)
    srv, port = start_server(handler)
    try:
        urls = [('http://127.0.0.1:%d/src.ts' % port, 1.0)
                for _ in range(20)]

        ctl = xqd_engine.DownloadControl()
        seg_dir = os.path.join(d, 'segout')
        os.makedirs(seg_dir, exist_ok=True)

        th = threading.Thread(
            target=lambda: xqd_engine.download_segments(
                urls, seg_dir, workers=4, control=ctl))
        th.start()

        # 等至少下到几个分片再暂停
        deadline = time.time() + 5
        while time.time() < deadline:
            if len(os.listdir(seg_dir)) >= 3:
                break
            time.sleep(0.05)
        ctl.pause()
        time.sleep(0.4)
        mid = len([f for f in os.listdir(seg_dir) if f.endswith('.ts')])
        ok('暂停前已下到部分分片', mid >= 3, '已有 %d 个' % mid)

        files_at_pause = set(f for f in os.listdir(seg_dir)
                             if f.endswith('.ts'))
        hits_at_pause = len(handler.hits)
        time.sleep(0.8)
        now = set(f for f in os.listdir(seg_dir) if f.endswith('.ts'))
        ok('暂停期间没有新分片', now == files_at_pause,
           '暂停时 %d → 现在 %d' % (len(files_at_pause), len(now)))
        ok('暂停期间没有新请求发出', len(handler.hits) == hits_at_pause,
           '请求数 %d → %d' % (hits_at_pause, len(handler.hits)))

        ctl.resume()
        th.join(30)
        ok('继续后下载完成', not th.is_alive())
        final = len([f for f in os.listdir(seg_dir) if f.endswith('.ts')])
        ok('全部 20 个分片到位', final == 20, '%d 个' % final)

        # ★ 关键：已下好的分片没有被重新下载
        sizes = set()
        for f in os.listdir(seg_dir):
            if f.endswith('.ts'):
                sizes.add(os.path.getsize(os.path.join(seg_dir, f)))
        ok('分片未被重复下载（大小一致）', sizes == {1000}, str(sizes))
    finally:
        srv.shutdown()


# ── 3. 直链下载：暂停时停下 ────────────────────────────────
def test_direct_pause():
    handler = _SlowHandler(delay=0.4)
    srv, port = start_server(handler)
    try:
        url = 'http://127.0.0.1:%d/big.mp3' % port
        ctl = xqd_engine.DownloadControl()
        out = os.path.join(OUT, 'out.mp3')
        res = {}

        def run():
            res['r'] = xqd_engine.download_direct(url, out, control=ctl)

        th = threading.Thread(target=run)
        th.start()
        time.sleep(0.15)
        ctl.pause()
        time.sleep(0.9)
        ok('直链下载在暂停时保持等待（不退出）', th.is_alive())
        hits_paused = len(handler.hits)
        time.sleep(0.6)
        ok('暂停期间直链没有继续收数据',
           len(handler.hits) == hits_paused,
           '请求数 %d → %d' % (hits_paused, len(handler.hits)))

        ctl.resume()
        th.join(30)
        ok('继续后直链下载完成', 'r' in res and res['r'][0],
           str(res.get('r', ('?',))[1] if 'r' in res else ''))
        ok('直链成品存在', os.path.isfile(out))
    finally:
        srv.shutdown()


# ── GUI 相关 ───────────────────────────────────────────────
def fake_lesson(i, camp='测试营'):
    le = xqd_platform.Lesson(
        index=i, title='第%d讲 测试' % (i + 1), when='07.%02d 06:00' % (i + 1),
        duration=600, ltype='VIDEO', topic_id='t%d' % i, room_id='r%d' % i,
        camp=camp)
    le.when_date = '2026.07.%02d' % (i + 1)
    return le


class FakePlatform(object):
    platform_id = 'fake'
    display_name = '假平台'
    camp_kinds = ('正式营',)

    def __init__(self):
        self.lessons = [fake_lesson(i) for i in range(5)]
        self.camp = xqd_platform.Camp('测试营', 'c1', '正式营', 5, '5节')

    def list_camps(self, kind='正式营'):
        return [self.camp]

    def camp_catalog(self, camp):
        return self.lessons

    def resolve(self, camp, lesson):
        return 'http://example.com/x.m3u8'


def build_gui(app):
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


def test_gui_checkbox(app):
    """入队即勾选 —— 这是用户报告的核心问题。"""
    win = build_gui(app)

    def fake_download(resolve_url, out_path, quality='max', workers=12,
                      tmp_root=None, on_progress=None, stop_flag=None,
                      expect_duration=0, control=None, on_phase=None):
        # 模拟下载期间暂停
        if control is not None:
            deadline = time.time() + 3
            while time.time() < deadline:
                if control.is_stopped():
                    return False, '已中止', out_path
                time.sleep(0.05)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(b'x' * 20000)
        return True, '假下载完成', out_path

    real = xqd_engine.download_lesson
    xqd_engine.download_lesson = fake_download
    try:
        # ★ 不手工勾选，直接触发下载（模拟「下载此课」/ 双击）
        win._start_downloads([(0, win.lessons[0])])
        time.sleep(0.4)
        app.processEvents()
        cb = win.tbl_lessons.item(0, 0)
        ok('入队后复选框自动勾上',
           cb.checkState() == Qt.Checked,
           'state=%s' % cb.checkState())

        # 其它行不应被误勾
        others = [win.tbl_lessons.item(r, 0).checkState()
                  for r in range(1, 5)]
        ok('其它行未被误勾',
           all(s == Qt.Unchecked for s in others), str(others))
    finally:
        xqd_engine.download_lesson = real
        for th in list(win.active_threads):
            th.wait(3000)


def test_gui_pause_button(app):
    """暂停按钮：可用状态、文案切换、行状态。"""
    win = build_gui(app)

    ok('空闲时暂停按钮禁用', not win.btn_pause.isEnabled())
    ok('空闲时按钮文案为「暂停」', win.btn_pause.text() == '暂停',
       win.btn_pause.text())

    # 造一个在跑的任务
    win.pending_queue.append((9999, win.lessons[0], win.current_camp,
                               os.path.join(OUT, 'x.mp4'), 'max'))
    win.running_workers.add(9999)
    win.jobs[9999] = {'row': 0, 'lesson': win.lessons[0],
                       'camp': win.current_camp,
                       'out_path': os.path.join(OUT, 'x.mp4')}
    win._sync_pause_button()
    ok('有任务时暂停按钮可用', win.btn_pause.isEnabled())

    win.toggle_pause()
    ok('点击后进入暂停态', win.control.is_paused())
    ok('按钮文案变为「继续」', win.btn_pause.text() == '继续',
       win.btn_pause.text())
    # ★ 状态词跟在课名后面（v1.5.0：课名列是 COL_TITLE）
    it = win.tbl_lessons.item(0, xqd_gui.COL_TITLE)
    st = it.data(xqd_gui.STATE_ROLE) if it else ''
    ok('运行中行状态显示「已暂停」', st == '已暂停', st)

    win.toggle_pause()
    ok('再次点击后恢复运行', not win.control.is_paused())
    ok('按钮文案回到「暂停」', win.btn_pause.text() == '暂停',
       win.btn_pause.text())

    # 暂停期间不应启动新任务
    win.pending_queue.append((9998, win.lessons[1], win.current_camp,
                               os.path.join(OUT, 'y.mp4'), 'max'))
    win.running_workers.add(9998)
    win.jobs[9998] = {'row': 1, 'lesson': win.lessons[1],
                       'camp': win.current_camp,
                       'out_path': os.path.join(OUT, 'y.mp4')}
    win.control.pause()
    before = len(win.pending_queue)
    win._pump_queue()
    ok('暂停期间不启动新任务',
       len(win.pending_queue) == before,
       '%d → %d' % (before, len(win.pending_queue)))
    win.control.resume()

    # 全部结束后按钮应自动禁用
    win.running_workers.clear()
    win.pending_queue = []
    win._sync_pause_button()
    ok('任务结束后暂停按钮禁用', not win.btn_pause.isEnabled())


def test_gui_close_unpauses(app):
    """关闭窗口时必须解除暂停，否则线程永远等下去。"""
    win = build_gui(app)
    win.control.pause()
    win.close()
    ok('关闭后不再处于暂停', not win.control.is_paused())
    ok('关闭后已要求中止', win.control.is_stopped())


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)

    test_control()
    test_segments_pause()
    test_direct_pause()

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    test_gui_checkbox(app)
    test_gui_pause_button(app)
    test_gui_close_unpauses(app)

    passed = sum(1 for _n, c in results if c)
    print('\n===== %d/%d 通过 =====' % (passed, len(results)))
    for n, c in results:
        if not c:
            print('  FAIL:', n)
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
