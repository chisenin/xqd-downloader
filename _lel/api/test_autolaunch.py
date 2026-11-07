# -*- coding: utf-8 -*-
"""GUI 授权链路端到端验证：自动启停 MuMu + 授权后自动关闭。

用真实的 MuMuManager.exe，不 mock。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

import xqd_auth
import xqd_gui

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('[OK] ' if cond else '[FAIL]', name,
                       ('  ← ' + detail) if detail and not cond else ''))


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    xqd_gui._apply_cjk_font(app)

    state = {'phase': 0, 'closed_msg': '', 'auth_ok': False,
             'failed': '', 'status': []}

    win = xqd_gui.MainWindow()
    win.show()

    # 记录状态播报
    orig_status = win._on_auth_status
    def cap_status(text):
        state['status'].append(text)
        orig_status(text)
    win._on_auth_status = cap_status

    orig_closed = win._on_auth_closed
    def cap_closed(text):
        state['closed_msg'] = text
        orig_closed(text)
    win._on_auth_closed = cap_closed

    orig_ok = win._on_auth_ok
    def cap_ok(cookie):
        state['auth_ok'] = bool(cookie)
        orig_ok(cookie)
    win._on_auth_ok = cap_ok

    orig_failed = win._on_auth_failed
    def cap_failed(reason):
        state['failed'] = reason
        orig_failed(reason)
    win._on_auth_failed = cap_failed

    # 启动前状态
    mgr = xqd_auth.find_mumu_manager()
    was_main = xqd_auth.main_running()
    was_dev = xqd_auth.is_running(mgr)
    print('启动前：主程序=%s 设备=%s' % (was_main, was_dev))
    xqd_auth.reset_session()

    def poll():
        w = win.auth_worker
        if w and not w.isRunning() and not getattr(poll, '_done', False):
            poll._done = True
            print('授权线程已结束')
            evaluate()
            return
        # 打印最新状态
        if state['status']:
            last = state['status'][-1]
            if last != getattr(poll, '_last', None):
                poll._last = last
                print('   … %s' % last)

    def evaluate():
        print()
        print('状态播报：')
        for s in state['status']:
            print('   · %s' % s)
        print()
        print('授权成功:', state['auth_ok'])
        if state['failed']:
            print('失败原因:', state['failed'].splitlines()[0])
        print('收尾提示:', state['closed_msg'])

        if state['auth_ok']:
            check('拿到授权', True)
            check('授权后自动关闭已触发',
                  '关闭' in state['closed_msg'], state['closed_msg'])
            # 等关闭完成（MuMu shutdown 是异步的，实测约 28 秒）
            QTimer.singleShot(45000, verify_closed)
        else:
            # 未登录：设备必须保持开启（用户还要登录）
            check('未登录时保持设备开启（供用户登录）',
                  xqd_auth.is_running(mgr), '设备被关掉了')
            check('提示用户去模拟器登录',
                  '尚未登录' in state['failed'], state['failed'])
            app.quit()

    def verify_closed():
        dev = xqd_auth.is_running(mgr)
        main_running = xqd_auth.main_running()
        print()
        print('关闭后：主程序=%s 设备=%s' % (main_running, dev))
        check('安卓设备已关闭', not dev)
        check('MuMu 主程序已关闭', not main_running)
        app.quit()

    # 用例 A：模拟器未运行时自动拉起
    QTimer.singleShot(500, lambda: win.auto_check_auth())
    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(2000)
    QTimer.singleShot(600000, lambda: (print('超时'), app.quit()))
    app.exec_()

    print()
    print('%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：%s' % FAIL)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
