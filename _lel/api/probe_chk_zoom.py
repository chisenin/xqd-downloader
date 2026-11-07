# -*- coding: utf-8 -*-
"""放大渲染课程表第 0 列，看清勾选框到底长什么样。

对比三组：
  A) 未勾选
  B) 已勾选
  C) 已勾选 + 当前选中行
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import (QApplication, QTableWidget, QTableWidgetItem,
                               QHeaderView)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'chk_zoom.png')


def build(app, qss=None):
    if qss:
        app.setStyleSheet(qss)
    else:
        app.setStyle('Fusion')
    tbl = QTableWidget(4, 2)
    tbl.setHorizontalHeaderLabels(['', '课程'])
    tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    states = [Qt.Unchecked, Qt.Checked, Qt.Checked, Qt.Unchecked]
    for r in range(4):
        cb = QTableWidgetItem('')
        cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                    | Qt.ItemIsSelectable)
        cb.setCheckState(states[r])
        tbl.setItem(r, 0, cb)
        tbl.setItem(r, 1, QTableWidgetItem('第%d讲' % (r + 1)))
    tbl.setCurrentCell(2, 0)     # 第 2 行是「当前行」
    tbl.resize(300, 140)
    tbl.show()
    app.processEvents()
    return tbl


def zoom(tbl, path, scale=6):
    pm = tbl.grab()
    # 只取第 0 列
    w = tbl.columnWidth(0)
    h = tbl.rowHeight(0) * 4
    crop = pm.copy(0, 0, w, h)
    big = crop.scaled(w * scale, h * scale,
                      Qt.KeepAspectRatio, Qt.FastTransformation)
    big.save(path)
    print('saved', path, big.width(), 'x', big.height())


def main():
    app = QApplication(sys.argv)
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'chk_before.png')
    tbl = build(app)
    zoom(tbl, base)

    # 加 QSS indicator 规则后再渲染
    app2 = QApplication.instance()
    qss = """
    QTableWidget::indicator {
        width: 15px; height: 15px;
        border: 1px solid #b3c0d2; border-radius: 3px;
        background: #ffffff;
    }
    QTableWidget::indicator:checked {
        background: #3b6ea5; border: 1px solid #2f5d8f;
    }
    """
    tbl2 = build(app2, qss)
    zoom(tbl2, OUT)


if __name__ == '__main__':
    main()
