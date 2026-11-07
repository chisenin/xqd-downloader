# -*- coding: utf-8 -*-
"""GUI 端到端验证：真实走完「授权 -> 营列表 -> 课表 -> 下载 -> 任务表」。

这是对 GUI 的真实检验（不是 mock），会实际下载一节课到临时目录。
"""
import os
import tempfile
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QTableWidgetItem

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui

OUT_DIR = os.path.join(ROOT, 'state', 'gui_e2e')
os.makedirs(OUT_DIR, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle('Fusion')
xqd_gui._apply_cjk_font(app)

win = xqd_gui.MainWindow()
win.ed_out.setText(OUT_DIR)
win.resize(1280, 860)
win.show()

state = {'phase': 'auth', 't0': time.time(), 'done': False}


def check_auth():
    """真实授权：走 xqd_auth 的免 adbd 通道。"""
    import xqd_auth
    print('[1] 授权检测中…')
    try:
        mgr = xqd_auth.find_mumu_manager()
        cookie = xqd_auth.get_cookie_header(mgr)
        win._on_auth_ok(cookie)
        print('    授权 OK, cookie %d 字节' % len(cookie))
    except Exception as e:
        print('    授权失败:', e)
        win._on_auth_failed(str(e))
        app.quit()
        return

    # 等授权成功回调触发 load_camps
    QTimer.singleShot(2500, phase_camps)


def phase_camps():
    print('[2] 营列表：%d 个' % len(win.camps))
    if not win.camps:
        print('    营列表为空，终止')
        app.quit()
        return
    win.lst_camps.setCurrentRow(0)
    QTimer.singleShot(1800, phase_lessons)


def phase_lessons():
    camp = win.current_camp
    print('[3] 课表：%s 共 %d 节' % (camp.name, len(win.lessons)))
    if not win.lessons:
        app.quit()
        return
    # 找一节短的 VIDEO 课
    target = None
    for i, le in enumerate(win.lessons):
        if le.type == 'VIDEO' and 100 < le.duration < 900:
            target = i
            break
    if target is None:
        target = 0
    print('    选中第 %d 节：%s（%ss）' % (target + 1,
                                    win.lessons[target].title,
                                    win.lessons[target].duration))
    win.tbl_lessons.setCurrentCell(target, 1)
    win.tbl_lessons.item(target, 0).setCheckState(Qt.Checked)

    # 记下期望的成品路径
    used = win.used_names.setdefault(camp.name, set())
    from xqd_platform import course_filename
    expect = os.path.join(OUT_DIR, camp.name,
                          course_filename(win.lessons[target], used=used))
    state['expect'] = expect
    state['target_row'] = target
    print('    期望成品：%s' % expect)

    QTimer.singleShot(300, lambda: win.start_download_selected())


def phase_check():
    """等下载完成。"""
    if state['done']:
        return
    if 'target_row' not in state:
        QTimer.singleShot(1500, phase_check)
        return
    row = state['target_row']
    le = win.lesson_of_row.get(row)
    if le and le.state in ('done', 'failed'):
        print('[4] 下载结束：state=%s  message=%s' % (le.state, le.message))
        path = le.out_path
        ok = os.path.isfile(path) and os.path.getsize(path) > 10000
        print('    成品存在：%s  大小=%.1f MB'
              % (ok, os.path.getsize(path) / 1048576 if ok else 0))
        if ok:
            import xqd_engine
            print('    ffprobe：%s' % (xqd_engine.probe_info(path),))
        # 任务表
        print('[5] 下载管理区：%d 条任务' % win.tbl_tasks.rowCount())
        for r in range(win.tbl_tasks.rowCount()):
            print('    [%d] %s | %s | %s'
                  % (r, win.tbl_tasks.item(r, 1).text(),
                     win.tbl_tasks.item(r, 2).text(),
                     win.tbl_tasks.item(r, 3).text()))
        # 截图
        app.processEvents()
        time.sleep(0.5)
        shot = os.path.join(ROOT, 'state', 'gui_shots', '20_GUI真实下载后.png')
        win.grab().save(shot)
        print('    截图：%s' % shot)
        state['done'] = True
        app.quit()
        return
    if time.time() - state['t0'] > 300:
        print('    超时')
        app.quit()
        return
    QTimer.singleShot(1500, phase_check)


QTimer.singleShot(600, check_auth)
QTimer.singleShot(6000, phase_check)
app.exec_()
print('=== GUI 端到端验证结束 ===')
