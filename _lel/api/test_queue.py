# -*- coding: utf-8 -*-
"""GUI 下载队列限流 + job_id 绑定测试（不联网、不下载）。

验证：
  1. 勾选 N 节时，**同时运行**的 DownloadWorker 不超过 MAX_LESSON_WORKERS
  2. 队列按序出队，一节结束后下一节自动放行
  3. 重复点击「下载选中」不会把同一节课重复入队
  4. 关闭窗口会清空未开始的队列
  5. ★ 下载中切换营，完成状态不会落到**别的课**上（job_id 绑定）
"""
import os
import sys
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_platform

results = []


def ok(name, cond, extra=''):
    results.append((name, bool(cond), extra))
    print('%-48s %s %s' % (name, 'PASS' if cond else 'FAIL', extra))


class FakePlatform(object):
    """假平台：不联网，只给课表。"""

    def __init__(self, n=10):
        self.camp = xqd_platform.Camp('测试营', 'c1', '正式营', n)
        self.lessons = []
        for i in range(n):
            le = xqd_platform.Lesson(index=i, title='第%d节' % (i + 1),
                                     duration=100, ltype='VIDEO')
            le.when_date = '2026.01.01'
            le.camp = '测试营'
            self.lessons.append(le)

    def list_camps(self, kind='正式营'):
        return [self.camp]

    def camp_catalog(self, camp):
        return self.lessons

    def resolve(self, camp, lesson):
        return 'http://example.invalid/x.m3u8'


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    out = os.path.join(tempfile.gettempdir(), 'xqd_queue_test')
    if os.path.isdir(out):
        shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)

    win = xqd_gui.MainWindow()
    win.out_dir = out
    win.ed_out.setText(out)
    win.cookie = 'x'
    win.platform = FakePlatform(10)
    win.current_camp = win.platform.camp
    win.lessons = win.platform.lessons
    win.lesson_of_row = {i: le for i, le in enumerate(win.lessons)}
    win.row_of_lesson = {le.key: i for i, le in enumerate(win.lessons)}

    # 记录真实启动的 worker
    started = []
    orig_init = xqd_gui.DownloadWorker.__init__

    def patched_init(self, platform, camp, lesson, out_path, quality, job_id,
                     control=None, seg_dir=None, parent=None):
        orig_init(self, platform, camp, lesson, out_path, quality, job_id,
                  control=control, seg_dir=seg_dir, parent=parent)
        started.append(job_id)

    xqd_gui.DownloadWorker.__init__ = patched_init

    # ── 测试 1：并发上限 ──
    picked = list(enumerate(win.lessons))
    win._start_downloads(picked)

    limit = xqd_gui.MAX_LESSON_WORKERS
    ok('同时启动数 ≤ MAX_LESSON_WORKERS',
       len(started) <= limit, '启动=%d 上限=%d' % (len(started), limit))
    ok('运行中集合大小 = 启动数',
       len(win.running_workers) == len(started),
       'running=%d' % len(win.running_workers))
    ok('其余进入队列',
       len(win.pending_queue) == len(picked) - len(started),
       'queue=%d' % len(win.pending_queue))

    # ── 测试 2：重复入队被拒 ──
    n_before = len(win.pending_queue)
    win._start_downloads([(0, win.lessons[0])])
    ok('重复入队被拒（队列不增长）',
       len(win.pending_queue) == n_before,
       'queue %d → %d' % (n_before, len(win.pending_queue)))

    # ── 测试 3：结束后自动放行下一节 ──
    if started:
        job0 = started[0]
        win.running_workers.discard(job0)
        before = len(started)
        win._pump_queue()
        ok('完成一节后自动放行下一节',
           len(started) == before + 1,
           'started %d → %d' % (before, len(started)))
        ok('放行后仍不超上限',
           len(win.running_workers) <= limit,
           'running=%d' % len(win.running_workers))

    # ── 测试 4：切换营后完成状态不串行 ──
    # 模拟：下载进行中 → 切换到另一个营（课程表被重建，row 索引含义变了）
    job_id = started[0]
    job = win.jobs.get(job_id)
    old_row = job['row']
    old_lesson = job['lesson']

    # 重建课程表：模拟切营后 row 0 对应的是**另一节**课
    other = xqd_platform.Lesson(index=0, title='另一个营的第1节',
                                 duration=100, ltype='VIDEO')
    other.when_date = '2026.02.02'
    win.lesson_of_row = {0: other}

    win._on_download_ok(job_id, '测试完成', os.path.join(out, 'x.mp4'))

    ok('切营后：原课状态 = 已完成',
       old_lesson.state == 'done',
       'state=%s' % old_lesson.state)
    ok('切营后：新表那一行未被污染',
       other.state != 'done',
       'other.state=%s' % other.state)
    ok('切营后：原课输出路径已记录',
       bool(old_lesson.out_path),
       old_lesson.out_path)

    # ── 测试 5：关闭时清空队列 ──
    win.pending_queue = [(99, win.lessons[0], win.platform.camp, 'x.mp4',
                          'max')]
    win.close()
    ok('关闭窗口清空未开始的队列', len(win.pending_queue) == 0,
       'queue=%d' % len(win.pending_queue))

    xqd_gui.DownloadWorker.__init__ = orig_init

    print('\n%d/%d 通过' % (sum(1 for _, c, _ in results if c), len(results)))
    return 0 if all(c for _, c, _ in results) else 1


if __name__ == '__main__':
    sys.exit(main())
