# -*- coding: utf-8 -*-
"""生成「品牌区点击 → 使用说明与关于」的界面截图。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication

import xqd_gui

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'state', 'gui_shots')


def main():
    app = QApplication(sys.argv)
    win = xqd_gui.MainWindow()
    win.resize(1220, 800)
    win.show()
    app.processEvents()

    def shot(name, w):
        p = os.path.join(OUT, name)
        w.grab().save(p)
        print('截图:', p, os.path.getsize(p), 'bytes')

    # 1. 主窗口（顶栏无菜单栏）
    shot('about_menu.png', win)

    # 2. 合并对话框：上半 = 使用说明
    dlg = xqd_gui.HtmlDialog('使用说明与关于', xqd_gui.HELP_ABOUT_HTML, win,
                             width=700, height=640)
    dlg.show()
    app.processEvents()
    shot('help_about.png', dlg)

    # 3. 往下滚到底：下半 = 关于与致谢
    bar = dlg.view.verticalScrollBar()
    bar.setValue(bar.maximum())
    app.processEvents()
    shot('help_about_bottom.png', dlg)

    # 4. 鼠标悬停在品牌区上的样子（手型光标 + 提示）
    brand = win.findChild(xqd_gui.BrandBox)
    if brand is not None:
        print('品牌区:', brand.geometry(), '点击层:', brand.overlay.geometry())
        print('点击层提示:', brand.overlay.toolTip())

    dlg.close()
    win.close()
    print('完成')


if __name__ == '__main__':
    main()
