# -*- coding: utf-8 -*-
"""GUI 新功能端到端验证（用静态 Cookie，免模拟器）。

覆盖：
  1. 布局：营列表全高，下载管理/运行日志右移
  2. 表头全选勾选框（三态）
  3. 跳过已下载：第二次下载同��节 → 全部跳过
  4. 音频保真：AUDIO 课下载后仍是 mp3/m4a，不转 mp4
"""
import os
import sys
import json
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt, QPoint
from PySide6.QtGui import QPainter

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_platform
import xqd_engine

COOKIE = (
    'rsessionId=<RSESSION_ID>'
    '<RSESSION_ID_TAIL>; '
    'userId=<USER_ID>; cUserId=<C_USER_ID>; '
    'uid=<UID>; '
    'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')

OUT = os.path.join(tempfile.gettempdir(), 'xqd_gui_v2_test')
SHOTS = os.path.join(ROOT, 'state', 'gui_shots')

results = []


def ok(name, cond, extra=''):
    results.append((name, bool(cond), extra))
    print('%-42s %s %s' % (name, 'PASS' if cond else 'FAIL', extra))


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

    steps = []

    def step(fn):
        steps.append(fn)

    # ── 步骤 1：加载营 ──
    def s1():
        win.load_camps()
        ok('加载营列表', len(win.camps) == 9, '%d 个营' % len(win.camps))
        # 选一个含 AUDIO 的营：五行养生音乐（全 AUDIO）
        target = None
        for i, c in enumerate(win.camps):
            if '五行养生音乐' in c.name:
                target = i
        ok('找到五行养生音乐营', target is not None)
        win.lst_camps.setCurrentRow(target)
        ok('课程表已加载', len(win.lessons) == 10, '%d 节' % len(win.lessons))
        types = set(le.type for le in win.lessons)
        ok('该营全为 AUDIO', types == {'AUDIO'}, str(types))

    # ── 步骤 2：布局 + 表头 ──
    def s2():
        p_camp = win.lst_camps.mapTo(win, QPoint(0, 0))
        p_task = win.tbl_tasks.mapTo(win, QPoint(0, 0))
        p_log = win.txt_log.mapTo(win, QPoint(0, 0))
        p_less = win.tbl_lessons.mapTo(win, QPoint(0, 0))
        ok('营列表占满左列（全高）',
           win.lst_camps.height() > win.tbl_lessons.height() * 1.5,
           '营列表 %d vs 课程表 %d' % (win.lst_camps.height(),
                                      win.tbl_lessons.height()))
        ok('下载管理右移（与课程表左对齐）',
           p_task.x() == p_less.x(), 'task.x=%d lesson.x=%d'
           % (p_task.x(), p_less.x()))
        ok('运行日志右移（与课程表左对齐）',
           p_log.x() == p_less.x(), 'log.x=%d lesson.x=%d'
           % (p_log.x(), p_less.x()))
        ok('表头勾选框存在', win.hdr_lessons is not None)

        # 三态：全不选
        ok('表头初始态=none', win.hdr_lessons.state() == 'none',
           win.hdr_lessons.state())
        # 模拟点击表头 → 全选
        win.hdr_lessons.toggled.emit(True)
        checked = sum(1 for i in range(win.tbl_lessons.rowCount())
                      if win.tbl_lessons.item(i, 0)
                      and win.tbl_lessons.item(i, 0).checkState()
                      == Qt.Checked)
        ok('表头点击→全选生效', checked == win.tbl_lessons.rowCount(),
           '%d/%d' % (checked, win.tbl_lessons.rowCount()))
        ok('全选后表头态=all', win.hdr_lessons.state() == 'all',
           win.hdr_lessons.state())
        # 取消一格 → partial
        win.tbl_lessons.item(0, 0).setCheckState(Qt.Unchecked)
        ok('取消一格→表头态=partial',
           win.hdr_lessons.state() == 'partial', win.hdr_lessons.state())
        # 复原全选，准备下载
        win.hdr_lessons.toggled.emit(True)

    # ── 步骤 3：真实下载（含音频保真）──
    def s3():
        ok('音频课扩展名为 .mp3',
           xqd_platform.expected_ext(win.lessons[0]) == '.mp3',
           xqd_platform.expected_ext(win.lessons[0]))
        win._start_downloads(list(enumerate(win.lessons[:2])))

    # ── 步骤 4：等下载完 ──
    def s4():
        alive = [t for t in win.active_threads if t.isRunning()]
        if alive:
            return False
        files = []
        for dirpath, _, fns in os.walk(OUT):
            for fn in fns:
                files.append(os.path.join(dirpath, fn))
        vids = [f for f in files if f.lower().endswith('.mp4')]
        auds = [f for f in files if f.lower().endswith(('.mp3', '.m4a'))]
        ok('下载产出 2 个文件', len(files) == 2, '%d 个：%s'
           % (len(files), [os.path.basename(f) for f in files]))
        ok('音频未被转成 MP4', len(vids) == 0 and len(auds) == 2,
           'mp4=%d mp3/m4a=%d' % (len(vids), len(auds)))
        # 校验每个音频真实格式与时长
        for f in auds:
            info = xqd_engine.probe_media(f)
            dur = info['duration']
            ok('音频可解析且有音轨 %s'
               % os.path.basename(f)[:18],
               info['has_audio'] and dur > 0,
               '容器=%s 编码=%s 时长=%.1fs'
               % (info['format_name'], info['codecs'], dur))
        return True

    # ── 步骤 5：跳过已下载 ──
    def s5():
        # 重新加载课表（触发异步扫描）
        win.load_lessons()
        if win.scan_worker and win.scan_worker.isRunning():
            win.scan_worker.wait(30000)
        # wait() 只保证线程结束，跨线程信号还要跑一遍事件循环才被处理
        app.processEvents()
        exist_rows = [i for i in range(win.tbl_lessons.rowCount())
                      if win.lesson_of_row[i].state == 'exists']
        ok('扫描出 2 节已存在', len(exist_rows) == 2,
           '实际 %d 节' % len(exist_rows))
        ok('已存在的课未勾选',
           all(win.tbl_lessons.item(i, 0).checkState() == Qt.Unchecked
               for i in exist_rows))
        txt = win.tbl_lessons.item(exist_rows[0], 1).text() if exist_rows else ''
        ok('已存在的课有[已存在]标记', '[已存在]' in txt, txt)
        ok('提示条显示已存在数量', '已有' in win.lbl_exist.text(),
           win.lbl_exist.text())

        # 手动勾选并下载 → 应该全部被跳过
        for i in exist_rows:
            win.tbl_lessons.item(i, 0).setCheckState(Qt.Checked)
        before = len(win.active_threads)
        win._start_downloads([(i, win.lesson_of_row[i]) for i in exist_rows])
        ok('重复下载被跳过（未启动新线程）',
           len(win.active_threads) == before,
           '线程数 %d → %d' % (before, len(win.active_threads)))

    # ── 步骤 6：截图 ──
    def s6():
        os.makedirs(SHOTS, exist_ok=True)
        p = os.path.join(SHOTS, '40_新版界面.png')
        win.grab().save(p)
        print('截图:', p)
        return True

    state = {'i': 0}
    plan = [s1, s2, s3, s4, s5, s6]

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
            # 需要等待，回到本步骤
            state['i'] -= 1
        QTimer.singleShot(1200 if r is not True or state['i'] > 3 else 300,
                          tick)

    QTimer.singleShot(600, tick)
    app.exec()

    print('\n' + '=' * 60)
    passed = sum(1 for _, c, _ in results if c)
    print('结果：%d/%d 通过' % (passed, len(results)))
    for n, c, e in results:
        if not c:
            print('  FAIL: %s  %s' % (n, e))
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
