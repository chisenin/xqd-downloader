# -*- coding: utf-8 -*-
"""「品牌区点击 → 使用说明与关于」测试。

覆盖：
  · 顶部**没有**菜单栏（不再占空间）
  · 品牌区有一个透明点击层，铺满整块区域
  · 点击它能打开合并对话框（上半用法 / 下半关于）
  · 合并内容含关键段落与 GitHub 地址
  · Ctrl+Q 退出快捷键仍在（按要求不加 F1）
"""
import os
import tempfile
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import Qt, QTimer

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui

PASS = []
FAIL = []


def ok(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('OK  ' if cond else 'FAIL', name,
                       ('  -> %s' % (extra,)) if extra else ''))


def main():
    app = QApplication(sys.argv)
    win = xqd_gui.MainWindow()

    # ── 1. 顶部不再有菜单栏 ────────────────────────────────
    bar = win.menuBar()
    titles = [a.text() for a in bar.actions()]
    ok('没有「帮助」菜单', '帮助' not in titles, titles)
    ok('菜单栏不占空间（无任何菜单项）', not titles, titles)
    ok('菜单栏不可见', not bar.isVisible(), bar.isVisible())

    # ── 2. 品牌区的透明点击层 ─────────────────────────────
    brand = win.findChild(xqd_gui.BrandBox)
    ok('存在品牌区控件', brand is not None)
    if brand is None:
        win.close()
        print('\n========================================================')
        print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
        print('失败项：', FAIL)
        return 1

    ov = brand.overlay
    ok('品牌区有透明点击层', isinstance(ov, xqd_gui.ClickOverlay))
    ok('点击层是透明的（不填背景）', not ov.autoFillBackground())
    ok('点击层用鼠标手型提示可点',
       ov.cursor().shape() == Qt.PointingHandCursor,
       ov.cursor().shape())
    ok('点击层有提示文字', '使用说明' in ov.toolTip(), ov.toolTip())

    win.show()
    app.processEvents()
    win.resize(1220, 800)
    app.processEvents()
    ok('点击层覆盖品牌区全部',
       ov.geometry() == brand.rect(),
       '%s vs %s' % (ov.geometry(), brand.rect()))
    ok('点击层宽度覆盖主标题',
       ov.width() >= brand.width(),
       '%d / %d' % (ov.width(), brand.width()))

    labels = brand.findChildren(QLabel)
    ok('品牌区有标题和副标题两行文字', len(labels) >= 2, len(labels))

    # ── 3. 点击能弹出对话框 ───────────────────────────────
    opened = []

    def auto_close():
        for w in app.topLevelWidgets():
            if isinstance(w, xqd_gui.HtmlDialog):
                opened.append(w.windowTitle())
                w.close()

    t = QTimer()
    t.timeout.connect(auto_close)
    t.start(120)

    # 模拟真实鼠标点击点击层
    from PySide6.QtTest import QTest
    QTest.mouseClick(ov, Qt.LeftButton)
    ok('点击点击层弹出对话框', bool(opened), opened)

    win.show_help_about()
    ok('show_help_about 可用', len(opened) >= 1, opened)
    t.stop()

    ok('对话框标题是「使用说明与关于」',
       any('使用说明' in x and '关于' in x for x in opened), opened)

    # ── 4. 合并内容 ───────────────────────────────────────
    h = xqd_gui.HELP_ABOUT_HTML
    for kw in ('授权', '营列表', '勾选课程', '下载目录',
               '开始下载', '输出结构'):
        ok('含用法「%s」' % kw, kw in h)
    ok('提到暂停', '暂停' in h)

    ok('含工具名', '兴趣岛视频下载器' in h)
    ok('含版本号', xqd_gui.APP_VERSION in h)

    gh = 'https://github.com/Xue-Wu-Zhi/xuewuzhi-downloader'
    ok('含学无止 GitHub 地址', gh in h)
    ok('提到 MIT', 'MIT' in h)
    ok('提到 PySide6', 'PySide6' in h)
    ok('提到 FFmpeg', 'FFmpeg' in h)
    ok('提到 pycryptodome', 'pycryptodome' in h)
    ok('有「特别声明」', '特别声明' in h)
    ok('声明不含其客户端代码', '不含其客户端代码' in h)
    ok('不含已失效的 PyJun/Mooc_Downloader 地址',
       'PyJun/Mooc_Downloader' not in h)

    # ★ 用法在上半、关于在下半（往下拉才看到）
    ok('用法在关于之前（上半部分）',
       h.index('使用说明') < h.index('关于本工具'),
       '%d vs %d' % (h.index('使用说明'), h.index('关于本工具')))

    # ── 5. Ctrl+Q 退出仍在 ────────────────────────────────
    acts = win.actions()
    quit_act = None
    for a in acts:
        if a.shortcut().toString() == 'Ctrl+Q':
            quit_act = a
    ok('Ctrl+Q 退出快捷键仍在', quit_act is not None,
       [a.text() for a in acts])
    ok('没有 F1 快捷键（按要求不加）',
       not any(a.shortcut().toString() == 'F1' for a in acts),
       [a.shortcut().toString() for a in acts])

    win.close()

    print('\n========================================================')
    print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：', FAIL)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
