# -*- coding: utf-8 -*-
"""验证：QTableWidget 行的 checkbox 在「选中行」时是否丢失对勾。

对比：同一张表里，行 0 未选中、行 1 选中，两者都 Checked。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import (QApplication, QTableWidget, QTableWidgetItem,
                               QStyle, QStyleOptionButton, QStylePainter)
from PySide6.QtCore import Qt

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'chk_render.png')


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    tbl = QTableWidget(3, 2)
    tbl.setHorizontalHeaderLabels(['', '课程'])
    for r in range(3):
        cb = QTableWidgetItem('')
        cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                    | Qt.ItemIsSelectable)
        cb.setCheckState(Qt.Checked if r < 2 else Qt.Unchecked)
        tbl.setItem(r, 0, cb)
        tbl.setItem(r, 1, QTableWidgetItem('第%d讲' % (r + 1)))
    tbl.resize(240, 120)
    tbl.setCurrentCell(1, 0)      # 选中第 1 行
    tbl.show()
    app.processEvents()

    # 直接用 style 渲染 checkbox indicator，看未选中/选中两种是否不同
    opt = QStyleOptionButton()
    opt.state = QStyle.State_On | QStyle.State_Enabled
    p = QStylePainter()
    from PySide6.QtGui import QPixmap, QColor
    pm = QPixmap(20, 20)
    pm.fill(QColor('#ffffff'))
    p.begin(pm, tbl)
    tbl.style().drawPrimitive(QStyle.PE_IndicatorCheckBox, opt, p, tbl)
    p.end()
    pm.save(OUT.replace('.png', '_checked.png'))

    opt2 = QStyleOptionButton()
    opt2.state = QStyle.State_On | QStyle.State_Enabled | QStyle.State_Selected
    pm2 = QPixmap(20, 20)
    pm2.fill(QColor('#e8f0fa'))
    p2 = QStylePainter()
    p2.begin(pm2, tbl)
    tbl.style().drawPrimitive(QStyle.PE_IndicatorCheckBox, opt2, p2, tbl)
    p2.end()
    pm2.save(OUT.replace('.png', '_selected.png'))

    tbl.grab().save(OUT)
    print('saved', OUT)


if __name__ == '__main__':
    main()
