# -*- coding: utf-8 -*-
"""裁剪用户截图里的复选框区域并放大。"""
import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

SRC = sys.argv[1] if len(sys.argv) > 1 else (
    r'C:\Users\chise\.workbuddy\clipboard-images'
    r'\clipboard-2026-11-07T03-16-39-152Z-a5606aba.png')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'user_shot_zoom.png')

app = QApplication(sys.argv)
pm = QPixmap(SRC)
print('原图', pm.width(), 'x', pm.height())

# 课程表复选框列 x≈280..300, 行 01/02 y≈205..245
crop = pm.copy(278, 200, 26, 50).scaled(
    26 * 10, 50 * 10, Qt.KeepAspectRatio, Qt.FastTransformation)
crop.save(OUT)
print('saved', OUT)

# 下载管理表复选框 x≈282..300, y≈480..530
crop2 = pm.copy(278, 478, 26, 52).scaled(
    26 * 10, 52 * 10, Qt.KeepAspectRatio, Qt.FastTransformation)
crop2.save(OUT.replace('.png', '_task.png'))
print('saved task')
