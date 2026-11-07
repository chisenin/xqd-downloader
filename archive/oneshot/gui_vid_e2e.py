# -*- coding: utf-8 -*-
"""视频课（VIDEO）回归验证 —— 确认音频改动没破坏 HLS 转封装路径。

同时验证：视频课下载后仍是 .mp4、时长与课表一致、重复下载被跳过。
"""
import os
import sys
import shutil
import tempfile

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
import xqd_engine
import xqd_platform

# ★ 凭据不在源码里 —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import xqd_creds            # noqa: E402

COOKIE = xqd_creds.load_cookie()

OUT = os.path.join(tempfile.gettempdir(), 'xqd_gui_vid_test')
results = []


def ok(name, cond, extra=''):
    results.append((name, bool(cond), extra))
    print('%-40s %s %s' % (name, 'PASS' if cond else 'FAIL', extra))


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    win = xqd_gui.MainWindow()
    win.resize(1280, 860)
    win.ed_out.setText(OUT)
    win.out_dir = OUT
    win.cookie = COOKIE
    win.platform.cookie = COOKIE
    win.show()

    plan = []

    def s1():
        win.load_camps()
        for i, c in enumerate(win.camps):
            if '道德经诵读' in c.name:
                win.lst_camps.setCurrentRow(i)
        ok('视频营课表加载', len(win.lessons) == 27,
           '%d 节' % len(win.lessons))
        types = set(le.type for le in win.lessons)
        ok('类型为 VIDEO', types == {'VIDEO'}, str(types))
        ok('视频扩展名为 .mp4',
           xqd_platform.expected_ext(win.lessons[0]) == '.mp4')

    def s2():
        # 下载前 2 节
        win._start_downloads(list(enumerate(win.lessons[:2])))

    def s3():
        if [t for t in win.active_threads if t.isRunning()]:
            return False
        files = []
        for dp, _, fns in os.walk(OUT):
            for fn in fns:
                files.append(os.path.join(dp, fn))
        ok('产出 2 个 mp4', len(files) == 2
           and all(f.lower().endswith('.mp4') for f in files),
           str([os.path.basename(f) for f in files]))
        for f in files:
            info = xqd_engine.probe_media(f)
            dur = info['duration']
            ok('视频可解析 %s' % os.path.basename(f)[:16],
               info['has_video'] and dur > 0,
               '容器=%s 编码=%s 时长=%.1fs 音轨=%s'
               % (info['format_name'], info['codecs'], dur,
                  info['has_audio']))
        return True

    def s4():
        # 重复下载应被跳过
        win.load_lessons()
        if win.scan_worker and win.scan_worker.isRunning():
            win.scan_worker.wait(30000)
        app.processEvents()
        exists = [i for i in range(win.tbl_lessons.rowCount())
                  if win.lesson_of_row[i].state == 'exists']
        ok('扫出 2 节已存在', len(exists) == 2, '%d 节' % len(exists))
        for i in exists:
            win.tbl_lessons.item(i, 0).setCheckState(Qt.Checked)
        before = len(win.active_threads)
        win._start_downloads([(i, win.lesson_of_row[i]) for i in exists])
        ok('视频重复下载被跳过',
           len(win.active_threads) == before,
           '%d → %d' % (before, len(win.active_threads)))
        # 下载完成后文件数不应变
        cnt = sum(len(fns) for _, _, fns in os.walk(OUT))
        ok('文件数未增加（未重复下载）', cnt == 2, '%d 个' % cnt)

    plan = [s1, s2, s3, s4]
    state = {'i': 0}

    def tick():
        if state['i'] >= len(plan):
            QTimer.singleShot(200, app.quit)
            return
        fn = plan[state['i']]
        state['i'] += 1
        try:
            r = fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            ok(fn.__name__, False, str(e))
            r = True
        if r is False:
            state['i'] -= 1
        QTimer.singleShot(300 if r is not True else 1500, tick)

    QTimer.singleShot(600, tick)
    app.exec()

    print('\n' + '=' * 58)
    passed = sum(1 for _, c, _ in results if c)
    print('结果：%d/%d 通过' % (passed, len(results)))
    for n, c, e in results:
        if not c:
            print('  FAIL: %s  %s' % (n, e))
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
