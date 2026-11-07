# -*- coding: utf-8 -*-
"""GUI 需求 2、3 端到端验证。

需求 2：遇到已下载资源 → **不弹窗**，只在日志里显示，自动跳过
需求 3：重复下载产生的 `-1` 文件名 → 完整则跳过，残缺则删除后覆盖重下

用真实下载 + 真实文件状态，不 mock。
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
import xqd_platform
import xqd_engine

COOKIE = (
    'rsessionId=<RSESSION_ID>'
    '<RSESSION_ID_TAIL>; '
    'userId=<USER_ID>; cUserId=<C_USER_ID>; '
    'uid=<UID>; '
    'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')

OUT = os.path.join(tempfile.gettempdir(), 'xqd_gui_v3_test')
results = []


def ok(name, cond, extra=''):
    results.append((name, bool(cond), extra))
    print('%-46s %s %s' % (name, 'PASS' if cond else 'FAIL', extra))


def listfiles():
    out = []
    for dp, _, fns in os.walk(OUT):
        for fn in fns:
            if fn.lower().endswith(('.mp4', '.mp3', '.m4a')):
                out.append(os.path.join(dp, fn))
    return out


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
    # ★ 禁用自动授权线程：它会重载营列表/课表，干扰本测试的课表状态
    win.auto_check_auth = lambda: None
    win.show()

    # 拦截所有弹窗 —— 需求 2 说「不要弹出警告框」
    popups = []

    def trap(parent, title, text, *a, **kw):
        popups.append((title, text))
        print('   !!! 弹窗被触发：%s / %s' % (title, text))
        return None

    from PySide6.QtWidgets import QMessageBox
    orig_info = QMessageBox.information
    orig_warn = QMessageBox.warning
    orig_crit = QMessageBox.critical
    orig_quest = QMessageBox.question
    QMessageBox.information = staticmethod(trap)
    QMessageBox.warning = staticmethod(trap)
    QMessageBox.critical = staticmethod(trap)
    QMessageBox.question = staticmethod(trap)

    state = {'i': 0}
    camp_name = '五行养生音乐'

    def step(fn):
        try:
            r = fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            ok(fn.__name__, False, str(e))
            r = True
        # 返回 False = 本步还在等，下一 tick 重跑同一步（不推进索引）
        if r is not False:
            state['i'] += 1
        QTimer.singleShot(1500 if r is not True else 300, tick)

    # ── 1：加载营与课表 ──
    def s1():
        win.load_camps()
        idx = None
        for i, c in enumerate(win.camps):
            if camp_name in c.name:
                idx = i
        ok('找到目标营', idx is not None)
        win.lst_camps.setCurrentRow(idx)
        ok('课表已加载', len(win.lessons) == 10, '%d 节' % len(win.lessons))
        state['lesson0'] = win.lessons[0]
        return True

    # ── 2：真实下载第 1 节 ──
    def s2():
        win._start_downloads([(0, state['lesson0'])])
        return True

    # ── 3：等下载完 ──
    def s3():
        alive = [t for t in win.active_threads if t.isRunning()]
        if alive:
            return False
        files = listfiles()
        ok('第 1 节下载产出 1 个文件', len(files) == 1,
           '%s' % [os.path.basename(f) for f in files])
        stem = xqd_platform.lesson_stem(state['lesson0'])
        ok('文件名是规范名（无 -1 后缀）',
           not os.path.basename(files[0]).startswith(stem + '-'),
           os.path.basename(files[0]))
        state['stem'] = stem
        state['file'] = files[0] if files else None
        return True

    # ── 4：需求 2 —— 再次下载同一节，应跳过且不弹窗 ──
    def s4():
        popups.clear()
        before = len(win.active_threads)
        win._start_downloads([(0, state['lesson0'])])
        ok('需求2：已下载的课不启动新线程',
           len(win.active_threads) == before,
           '线程 %d → %d' % (before, len(win.active_threads)))
        ok('需求2：未弹出任何对话框', len(popups) == 0,
           '弹了 %d 个：%s' % (len(popups), popups))
        log_text = win.txt_log.toPlainText()
        ok('需求2：日志里记录了跳过',
           '跳过' in log_text,
           [l for l in log_text.splitlines() if '跳过' in l][-1:])
        ok('需求2：文件未被重复下载（仍是 1 个）',
           len(listfiles()) == 1,
           '%s' % [os.path.basename(f) for f in listfiles()])
        return True

    # ── 5：需求 3 —— 把文件弄成残缺 + 造一个 -1 文件 ──
    def s5():
        stem = state['stem']
        folder = os.path.dirname(state['file'])
        # 5a. 造一个 -1 后缀的重复文件（模拟旧工具留下的）
        dup = os.path.join(folder, stem + '-1.mp3')
        with open(dup, 'wb') as f:
            f.write(b'\x00' * 4096)
        # 5b. 把主文件也变成残缺（截断）
        with open(state['file'], 'r+b') as f:
            f.truncate(200)
        ok('准备：造出 -1 文件且主文件残缺',
           os.path.exists(dup) and os.path.getsize(state['file']) == 200,
           'dup=%d bytes, main=%d bytes'
           % (os.path.getsize(dup), os.path.getsize(state['file'])))
        # 重新扫描，应判定为「需重下」
        win.checker.invalidate()
        st = win.checker.check_group(folder, stem, state['lesson0'].duration)
        ok('残缺文件被判定为 broken', st['status'] == 'broken',
           '%s (%s)' % (st['status'], st.get('reason')))
        return True

    # ── 6：需求 3 —— 下载时应清理残件、覆盖重下 ──
    def s6():
        popups.clear()
        before = len(win.active_threads)
        win._start_downloads([(0, state['lesson0'])])
        ok('需求3：残缺文件触发了重新下载',
           len(win.active_threads) > before,
           '线程 %d → %d' % (before, len(win.active_threads)))
        log_text = win.txt_log.toPlainText()
        ok('需求3：日志里记录了清理残件',
           '清理残缺文件' in log_text,
           [l for l in log_text.splitlines() if '残缺' in l][-1:])
        return True

    # ── 7：等重下完成 ──
    def s7():
        alive = [t for t in win.active_threads if t.isRunning()]
        if alive:
            return False
        stem = state['stem']
        folder = os.path.dirname(state['file'])
        files = sorted(os.listdir(folder))
        media = [f for f in files if f.lower().endswith(('.mp3', '.m4a',
                                                         '.mp4'))]
        ok('需求3：重下后只有 1 个媒体文件（无 -1 重复）',
           len(media) == 1, '%s' % media)
        ok('需求3：文件名是规范名', media and not media[0].startswith(stem + '-'),
           media[0] if media else '')
        # 完整性校验
        full = os.path.join(folder, media[0])
        info = xqd_engine.probe_media(full)
        ok('需求3：重下的文件完整可解析',
           info['duration'] > 0 and info['has_audio'],
           '时长=%.1fs 编码=%s' % (info['duration'], info['codecs']))
        ok('需求3：未弹出对话框', len(popups) == 0, str(popups))
        return True

    # ── 8：需求 2 复验 —— 完整文件再次下载应跳过 ──
    def s8():
        popups.clear()
        before = len(win.active_threads)
        win._start_downloads([(0, state['lesson0'])])
        ok('复验：完整文件再次下载被跳过',
           len(win.active_threads) == before,
           '线程 %d → %d' % (before, len(win.active_threads)))
        ok('复验：未弹窗', len(popups) == 0, str(popups))
        return True

    plan = [s1, s2, s3, s4, s5, s6, s7, s8]

    def tick():
        if state['i'] >= len(plan):
            QTimer.singleShot(300, app.quit)
            return
        step(plan[state['i']])

    QTimer.singleShot(600, tick)
    app.exec()

    QMessageBox.information = orig_info
    QMessageBox.warning = orig_warn
    QMessageBox.critical = orig_crit
    QMessageBox.question = orig_quest

    print('\n' + '=' * 64)
    passed = sum(1 for _, c, _ in results if c)
    print('结果：%d/%d 通过' % (passed, len(results)))
    for n, c, e in results:
        if not c:
            print('  FAIL: %s  %s' % (n, e))
    shutil.rmtree(OUT, ignore_errors=True)
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
