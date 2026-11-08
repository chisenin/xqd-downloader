# -*- coding: utf-8 -*-
"""兴趣岛视频下载器（单文件 GUI）。

技术选型：PySide6（Qt）
----------------------
* 纯 Python 栈，与本项目已有的下载内核（xqd_engine / xqd_platform）同语言，
  不引入跨语言边界；
* QSS 样式表能做出现代扁平风格，比 Tkinter 漂亮一个量级；
* 可用 PyInstaller 打成单个 exe 交付；
* 扩展接口见 xqd_platform.Platform —— 新增平台只需写一个子类。

界面结构
--------
    ┌──────────────────────────────────────────────┐
    │ 顶栏：平台 · 授权状态 · 下载目录 · 设置       │
    ├───────────┬──────────────────────────────────┤
    │ 营列表    │ 课程列表（勾选 / 进度条 / 单项下载）│
    │           │                                  │
    ├───────────┴──────────────────────────────────┤
    │ 下载管理（任务列表 / 清除列表 / 删除文件）      │
    ├──────────────────────────────────────────────┤
    │ 状态栏：日志                                  │
    └──────────────────────────────────────────────┘
"""

import json
import os
import queue
import sys
import threading
import time
import traceback

from PySide6.QtCore import (Qt, QThread, QTimer, Signal, QSettings,
                            QSize, QRect)
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QIcon, QPainter,
                         QPen, QPalette)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QFileDialog,
                               QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QSplitter,
                               QSizePolicy, QStackedWidget, QStyle,
                               QStyleOptionViewItem, QStyledItemDelegate,
                               QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget)

import xqd_auth
import xqd_creds
import xqd_dedupe
import xqd_engine
import xqd_history
import xqd_platform

APP_TITLE = '兴趣岛视频下载器'
APP_VERSION = '1.5.3'

# ── 课程列表的列索引（★ 单一事实来源）─────────────────────────
#   v1.5.0 起共 6 列：勾选框后面第一列就是「标题前缀」（原营内序号）。
#   界面代码与测试一律引用这些常量，不要再写死 1/2/4 ——
#   加一列就要把所有硬编码列号改一遍，漏一个就是错位显示。
COL_CHECK = 0       # 勾选框（表头带「全选」复选框）
COL_PREFIX = 1      # 标题前缀：该课在**原营**课表里的序号
COL_TITLE = 2       # 课程：课名 + 跟在课名后面的状态词（自绘委托）
COL_SUFFIX = 3      # 标题后缀：成品文件名里的 YYYY.MM.DD
COL_DUR = 4         # 时长
COL_PROGRESS = 5    # 进度条
LESSON_COLUMN_COUNT = 6

# 多个营名之间的分隔（中文间隔号「·」，与界面标题风格一致）
CAMP_SEPARATOR = ' · '

# ── 配置 ─────────────────────────────────────────────────────

CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.xqd_tool')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

# ★ 下载历史（下载列表 + 下载进度）与分片缓存的路径在 **xqd_history** 里
#   （本模块一律通过 xqd_history.xxx() 访问，不重复定义常量 ——
#    两处定义容易改一处忘一处，路径就会对不上）。

# ★ 测试隔离：设这个环境变量后，配置 / 历史 / 分片缓存全部落到临时目录，
#   不会污染用户真实的 ~/.xqd_tool/。
#   （测试跑一次把用户的下载目录改成临时目录，是很难查的坑 —— 本轮就踩了。）
if os.environ.get('XQD_TEST_HOME'):
    CONFIG_DIR = os.environ['XQD_TEST_HOME']
    CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

# 历史版本的默认目录（用于识别「用户从没改过目录」）
_LEGACY_OUT_DIRS = (r'Z:\太极营', 'Z:/太极营')


def windows_download_dir():
    """Windows 的「下载」文件夹（用户文档重定向后的真实路径）。

    ★ 不能用 ``os.path.expanduser('~') + '/Downloads'``：
      本机 USERPROFILE 是 ``C:\\Users\\chise``，但用户的「下载」
      已被重定向到 ``D:\\user\\chisenin\\download``（见记忆里的
      「用户主目录/文档/视频等重定向到 D:\\user\\chisenin」）。

    取法（按优先级）：
      1. 注册表 ``User Shell Folders`` 的 Downloads GUID
         （``{374DE290-123F-4565-9164-39C4925E467B}``）—— 权威来源，
         能正确反映「文档」文件夹的重定向。
      2. 环境变量 ``USERPROFILE`` 拼 ``Downloads``。
      3. 硬编码 ``C:\\Users\\<user>\\Downloads``。
    """
    # 1) 注册表
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders')
        try:
            val, _t = winreg.QueryValueEx(
                key, '{374DE290-123F-4565-9164-39C4925E467B}')
        finally:
            winreg.CloseKey(key)
        p = os.path.expandvars(str(val)).rstrip('\\')
        if p and os.path.isdir(p):
            return p
        if p:
            return p
    except Exception:
        pass
    # 2) 环境变量
    home = os.environ.get('USERPROFILE') or os.path.expanduser('~')
    if home:
        p = os.path.join(home, 'Downloads')
        if os.path.isdir(p):
            return p
        return p
    # 3) 兜底
    return r'C:\Users\%s\Downloads' % (os.environ.get('USERNAME') or 'user')


def default_out_dir():
    """首次使用时的默认下载目录 = Windows 的「下载」文件夹。"""
    return windows_download_dir()


def load_config(path=None):
    """读配置。path=None 用默认的 CONFIG_FILE。

    ★ 支持传 path 是为了让**测试能隔离** —— 否则测试会写坏
      用户真实的 ~/.xqd_tool/config.json（下载目录被改成临时目录）。
    """
    path = path or CONFIG_FILE
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg, path=None):
    path = path or CONFIG_FILE
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('保存配置失败：', e)


# 课级并发上限（同时下载几节课）。
#
# 为什么必须限：勾选 N 节就起 N 个 DownloadWorker，每个再开 12 个分片
# 线程 —— 全选一个 70 节的营就是 840 条并发 HTTP 连接。实测 CDN 侧
# 单 IP 的吞吐上限约 8~10MB/s，连接数远超这个量时会出现
# 「大量分片超时 + 重试风暴」，反而比串行更慢更容易失败。
#
# 批处理（xqd_batch.py）实测稳定的是 3 路并发、每路 16 分片线程，
# 整体均速 ~10.5MB/s。这里对齐到 3 路。
MAX_LESSON_WORKERS = 3

# 每节课内部的分片并发数
SEGMENT_WORKERS = 12

# ── v1.5.0：封装阶段「流水线」──────────────────────────────────
# ★ 用户 2026-11-07 指出：一节即将下完、进入「封装」时，网络流量
#   已经被解放了 —— 拼接分片 / ffmpeg 转封装 / ffprobe 校验全程只读
#   本地磁盘，不再发一个 HTTP 请求。此时却还占着一个下载并发槽位，
#   队列里的下一节只能干等，带宽白白空着。
#
# 于是把「并发上限」拆成两种资源：
#   - **网络槽位**（MAX_LESSON_WORKERS=3）：只有 解析/下载 阶段占；
#   - **本地封装槽位**（MAX_MUX_WORKERS=2）：封装/校验 阶段占。
# 任务一进「封装」就把网络槽位还回去 → _pump_queue 立刻开下一节，
# 形成「A 在封装、B/C/D 在下载」的流水线，总耗时大约省下每段封装时间。
#
# ★ 为什么还要给封装单独设上限：成品写在 Z 盘（SMB 网络盘，实测
#   约 10 MB/s），cat 拼接 + ffmpeg 重封装都是连续大文件写入。若 5 节课
#   同时封装，磁盘互相抢 IO，反而把已下完的课拖慢，还会连累正在下
#   的分片落盘。2 路是「不空等、也不抢盘」的折中；超过上限的封装任务
#   暂时继续占着网络槽位，等有封装槽位空出来再释放（见 _release_idle_slots）。
LOCAL_PHASES = ('封装', '校验')
MAX_MUX_WORKERS = 2

# ══════════════════════════════════════════════════════════════
#  状态词表 —— **单一事实来源**
# ══════════════════════════════════════════════════════════════
#
# ★ 为什么要有这一张表（用户 2026-11-07 指出）：
#   同一节课会在**三个地方**显示状态 ——
#     ① 课程列表的「标题后缀」列
#     ② 下载管理表的「状态」列
#     ③ 运行日志
#   以前这三处各写各的词：课程列表只写粗粒度的「下载中…」，
#   下载管理写细分阶段「封装中」，日志只记「开始下载：xxx」。
#   结果同一节课在三处对不上号 —— 列表说在下载，管理表说在封装，
#   日志里根本查不到当前状态。
#
# ★ 规则：三处**必须用同一套词**，且课程列表的后缀要**跟着阶段实时变**。
#   引擎给的阶段名（解析/下载/封装/校验）→ 界面词（解析中/下载中/…）。
PHASE_TEXT = {
    '解析': '解析中',
    '下载': '下载中',
    '封装': '封装中',
    '校验': '校验中',
}

# 「下载管理」表状态列里表示**进行中**的所有文本。
# ★ 阶段之间必须能自由切换（解析中 → 下载中 → 封装中 → 校验中），
#   但终态（已完成 / 失败 / 排队中）不能被阶段刷新覆盖。
PHASE_TEXTS = ('下载中', '排队中', '解析中', '封装中', '校验中')

# 界面状态词全集（三处共用）
STATE_TEXTS = (
    '解析中', '下载中', '封装中', '校验中',
    '排队中', '已暂停', '已完成', '失败', '已存在', '需重下',
)

# 各状态的配色（用在课程名后面的状态词上）
STATE_COLORS = {
    '已完成': '#1f7a3d',
    '失败': '#c0392b',
    '已存在': '#7d8b9c',
    '需重下': '#c0392b',
    '排队中': '#8a7ab8',
    '已暂停': '#c07b2a',
    '下载中': '#3b6ea5',
    '下载中…': '#3b6ea5',
    '解析中': '#3b6ea5',
    '封装中': '#c07b2a',
    '校验中': '#8a7ab8',
}

# 课程列表第 1 列里，状态词存在 item 的哪个 role 上
# （Qt.DisplayRole 放纯课名，状态词单独存，委托才能分别着色）
STATE_ROLE = Qt.UserRole + 1


class LessonTitleDelegate(QStyledItemDelegate):
    """课程列表「课程」列：课名 + 紧跟其后的状态词。

    ★ 为什么需要自绘委托（用户 2026-11-07 要求）：
      状态词要**跟在标题后面**显示下载状态，但 QTableWidgetItem 只有
      一个前景色 —— 整格着色会把课名也染掉（老版本就是这样，
      「已完成」把整行课名都染绿）。
      这里把课名和状态词分成两段画：课名用主题色，状态词用
      STATE_COLORS 的状态色，两者颜色互不影响。
    """

    def paint(self, painter, option, index):
        title = index.data(Qt.DisplayRole) or ''
        state = index.data(STATE_ROLE) or ''

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else None

        # ① 先画背景（选中态 / 交替行色）
        opt.text = ''
        if style is not None:
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        if not title:
            return

        painter.save()
        fm = opt.fontMetrics
        rect = opt.rect.adjusted(6, 0, -6, 0)
        suffix = '  [%s]' % state if state else ''
        sfx_w = fm.horizontalAdvance(suffix)

        # ② 课名（可用宽度要留给状态词，否则长课名会把状态词挤出去）
        avail = max(rect.width() - sfx_w, 40)
        elided = fm.elidedText(title, Qt.ElideRight, avail)
        if opt.state & QStyle.State_Selected:
            painter.setPen(opt.palette.color(QPalette.HighlightedText))
        else:
            painter.setPen(opt.palette.color(QPalette.Text))
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

        # ③ 状态词（紧跟在课名后面）
        if suffix:
            color = STATE_COLORS.get(state)
            painter.setPen(QColor(color) if color
                           else opt.palette.color(QPalette.Text))
            x = rect.left() + fm.horizontalAdvance(elided) + 2
            painter.drawText(QRect(x, rect.top(), sfx_w, rect.height()),
                             Qt.AlignVCenter | Qt.AlignLeft, suffix)
        painter.restore()


class MarqueeLabel(QLabel):
    """课程列表标题里的「营名」：多个营时向左无缝循环滚动。

    ★ 为什么要滚动（用户 2026-11-07 要求）：
      勾选多个营后，营名串可能长达几十个字，标题栏放不下；
      截断（elide）只能看到头两个营，其余营名永远看不到。
      这里把整串画两遍、用定时器持续左移，移过一整串宽度后
      回到 0 → 视觉上是「一直向左、循环出现」。

    ★ 单营 / 短文本时不启动定时器，走 QLabel 默认绘制，
      这样 QSS 的配色、字体、对齐都不受影响。
    """

    STEP = 1          # 每次左移的像素
    INTERVAL = 35     # 毫秒（约 28px/s，中文两字/秒，看得清）
    WIDTH = 250       # 标题区固定宽度，避免长营名把按钮挤出窗口

    def __init__(self, parent=None):
        QLabel.__init__(self, parent)
        self._loop = ''
        self._offset = 0
        self._loop_w = 1
        self._scroll = False
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL)
        self._timer.timeout.connect(self._tick)

    def set_marquee(self, text, scroll=False, tooltip=''):
        """设置标题文字。``text()`` 始终返回完整串（测试 / 提示可用）。"""
        self.setText(text)
        self.setToolTip(tooltip or text)
        self._scroll = False
        self._timer.stop()
        self._offset = 0
        if scroll and text:
            # 末尾补一段分隔，滚到末尾时才能无缝接回开头
            self._loop = text + CAMP_SEPARATOR
            self._loop_w = max(
                1, self.fontMetrics().horizontalAdvance(self._loop))
            # 短文本能完整显示就不必滚（滚动反而看不清）
            self._scroll = self._loop_w > self.width()
            if self._scroll:
                self._timer.start()
        self.update()

    def _tick(self):
        self._offset = (self._offset + self.STEP) % self._loop_w
        self.update()

    def paintEvent(self, ev):
        if not self._scroll:
            QLabel.paintEvent(self, ev)
            return
        p = QPainter(self)
        p.setClipRect(self.rect())
        p.setFont(self.font())
        p.setPen(QColor('#2f3d52'))   # 与 QSS ``#SectionTitle`` 同色
        fm = self.fontMetrics()
        y = (self.height() - fm.height()) // 2 + fm.ascent()
        x = -self._offset
        while x < self.width():
            p.drawText(int(x), int(y), self._loop)
            x += self._loop_w
        p.end()


# ══════════════════════════════════════════════════════════════
#  QSS 样式
# ══════════════════════════════════════════════════════════════

QSS = """
QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #2b3445;
}
QMainWindow, QDialog { background: #f4f6fa; }

/* 菜单栏：和顶栏同色 → 视觉上连成一条蓝带 */
#TopBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #3b6ea5, stop:1 #2f5d8f);
    border: none;
}
#TopBar QLabel { color: #ffffff; }
#Brand { font-size: 16px; font-weight: 600; }
#BrandSub { color: #c8dcf0; font-size: 11px; }

QPushButton {
    background: #ffffff;
    border: 1px solid #d3dae6;
    border-radius: 6px;
    padding: 6px 14px;
    color: #33415c;
}
QPushButton:hover { background: #eef3fa; border-color: #9fb6d4; }
QPushButton:pressed { background: #dde8f5; }
QPushButton:disabled { background: #eef0f4; color: #a8b2c1; border-color: #e0e4ea; }

QPushButton#Primary {
    background: #3b6ea5; border: none; color: #ffffff; font-weight: 500;
}
QPushButton#Primary:hover { background: #4a7fb8; }
QPushButton#Primary:pressed { background: #2f5d8f; }
QPushButton#Primary:disabled { background: #a9bdd4; color: #eef3f8; }

QPushButton#Danger { color: #c0392b; border-color: #e8c4bf; }
QPushButton#Danger:hover { background: #fdf0ee; border-color: #d98d84; }

/* 暂停按钮：橙色系，和「下载」的蓝色主按钮区分开 */
QPushButton#PauseBtn {
    background: #fdf6ec; border: 1px solid #e8d5b8; color: #9a6a24;
}
QPushButton#PauseBtn:hover { background: #f9ead4; border-color: #d9bd8e; }
QPushButton#PauseBtn:pressed { background: #f2dfc0; }
QPushButton#PauseBtn:disabled { background: #f2f3f5; color: #b4bcc8; border-color: #e2e6ec; }

QLineEdit {
    background: #ffffff; border: 1px solid #d3dae6; border-radius: 6px;
    padding: 6px 10px; selection-background-color: #3b6ea5;
}
QLineEdit:focus { border-color: #3b6ea5; }

QComboBox {
    background: #ffffff; border: 1px solid #d3dae6; border-radius: 6px;
    padding: 5px 10px; min-height: 20px;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: none; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid #7b8a9e;
    margin-right: 8px;
}

QTableWidget {
    background: #ffffff; border: 1px solid #e0e5ee; border-radius: 8px;
    gridline-color: #eef1f6; alternate-background-color: #fafbfd;
}
QTableWidget::item { padding: 4px 6px; border: none; }
QTableWidget::item:selected { background: #e8f0fa; color: #1f2d3f; }
QHeaderView::section {
    background: #eef2f8; color: #4a5a72; padding: 7px 8px;
    border: none; border-right: 1px solid #e0e5ee;
    border-bottom: 1px solid #dde3ec; font-weight: 600;
}
QHeaderView::section:first { border-top-left-radius: 8px; }
QHeaderView::section:last { border-top-right-radius: 8px; }

QListWidget {
    background: #ffffff; border: 1px solid #e0e5ee; border-radius: 8px;
    outline: none; padding: 4px;
}
QListWidget::item { padding: 9px 10px; border-radius: 6px; margin: 1px 3px; }
QListWidget::item:hover { background: #f0f5fb; }
QListWidget::item:selected { background: #3b6ea5; color: #ffffff; }
QListWidget::item:selected:hover { background: #35648f; }

QProgressBar {
    border: none; border-radius: 4px; background: #e8ecf3;
    height: 8px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #4a90c9, stop:1 #3b6ea5); border-radius: 4px; }

QPlainTextEdit {
    background: #1f2733; color: #c9d6e5; border: none;
    font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px;
    padding: 8px;
}

QStatusBar { background: #e8edf5; color: #4a5a72; }
QStatusBar::item { border: none; }

#Card {
    background: #ffffff; border: 1px solid #e0e5ee; border-radius: 10px;
}
#SectionTitle { font-size: 13px; font-weight: 600; color: #2f3d52; }
#Muted { color: #8494a8; font-size: 11px; }
#Banner {
    background: #fff8e6; border: 1px solid #f0dfae; border-radius: 8px;
    color: #8a6d1a; padding: 10px 12px;
}
#BannerOk {
    background: #eaf7ee; border: 1px solid #b8e0c4; border-radius: 8px;
    color: #1f7a3d; padding: 10px 12px;
}
#BannerErr {
    background: #fdeeee; border: 1px solid #f0c2c2; border-radius: 8px;
    color: #b03030; padding: 10px 12px;
}
QTabWidget::pane { border: 1px solid #e0e5ee; border-radius: 8px; top: -1px; }
QTabBar::tab {
    background: transparent; padding: 7px 18px; margin-right: 2px;
    border: 1px solid transparent; border-top-left-radius: 7px;
    border-top-right-radius: 7px; color: #6a7a90;
}
QTabBar::tab:selected {
    background: #ffffff; color: #2f5d8f; font-weight: 600;
    border-color: #e0e5ee; border-bottom-color: #ffffff;
}
QSplitter::handle { background: #e8edf5; width: 4px; }
"""


# ══════════════════════════════════════════════════════════════
#  表格内嵌进度条
# ══════════════════════════════════════════════════════════════

class CellProgressBar(QProgressBar):
    """放进表格单元格的迷你进度条。"""

    def __init__(self, parent=None):
        QProgressBar.__init__(self, parent)
        self.setRange(0, 100)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(10)
        self.setMinimumWidth(60)


class CheckHeaderView(QHeaderView):
    """在表头第 0 列绘制一个「全选」复选框。

    QHeaderView 不支持嵌入子控件（setIndexWidget 是 QTreeView 的能力），
    所以只能自绘 + 自己处理点击。

    三态：
      none     全不选（空心方框）
      partial  部分选中（方框内一条横线）
      all      全选（方框内对勾，蓝色实心）
    """

    toggled = Signal(bool)          # True = 请求全选，False = 请求全不选

    def __init__(self, parent=None):
        QHeaderView.__init__(self, Qt.Horizontal, parent)
        self._state = 'none'
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.setDefaultAlignment(Qt.AlignCenter)

    # ── 状态 ──
    def set_state(self, state):
        if state not in ('none', 'partial', 'all'):
            state = 'none'
        if state != self._state:
            self._state = state
            self.viewport().update()

    def state(self):
        return self._state

    # ── 绘制 ──
    def paintSection(self, painter, rect, logical_index):
        """绘制表头。

        ⚠️ PySide6 的签名是 (painter, rect, logicalIndex: int)，
        **不是** QModelIndex —— 传 int。
        """
        QHeaderView.paintSection(self, painter, rect, logical_index)
        if logical_index != 0:
            return

        s = 14
        box = rect.center().x() - s // 2
        by = rect.center().y() - s // 2
        r = QRect(box, by, s, s)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._state == 'all':
            painter.setBrush(QColor('#3b6ea5'))
            painter.setPen(QPen(QColor('#3b6ea5'), 1))
        else:
            painter.setBrush(QColor('#ffffff'))
            painter.setPen(QPen(QColor('#8b9bb0'), 1))
        painter.drawRoundedRect(r, 3, 3)

        if self._state == 'all':
            painter.setPen(QPen(QColor('#ffffff'), 2))
            painter.drawLine(r.left() + 3, r.center().y(),
                             r.left() + 6, r.bottom() - 4)
            painter.drawLine(r.left() + 6, r.bottom() - 4,
                             r.right() - 3, r.top() + 3)
        elif self._state == 'partial':
            painter.setPen(QPen(QColor('#3b6ea5'), 2))
            painter.drawLine(r.left() + 3, r.center().y(),
                             r.right() - 3, r.center().y())
        painter.restore()

    # ── 点击 ──
    def mousePressEvent(self, event):
        idx = self.logicalIndexAt(event.position().toPoint())
        if idx == 0:
            self.toggled.emit(self._state != 'all')
            event.accept()
            return
        QHeaderView.mousePressEvent(self, event)

# ══════════════════════════════════════════════════════════════
#  授权工作线程
# ══════════════════════════════════════════════════════════════

class AuthWorker(QThread):
    """在后台做授权检测，避免阻塞 UI。

    流程：定位 MuMu → 确保主程序在跑 → 确保安卓设备在跑 →
    读 App 的 Cookie 拿授权。

    授权拿到后**自动关闭**本工具启动的 MuMu 与 App（工具后续全靠
    Cookie 直连网关，不再需要模拟器）。若模拟器是用户自己开的，
    则不关 —— 只提示用户可以关。

    注意：App 未登录时不能关（用户还要在模拟器里登录），
    这种情况下设备保持开启，等用户登录后点「重试」。
    """

    status = Signal(str)
    ok = Signal(str)          # cookie header
    failed = Signal(str)      # 原因
    closed = Signal(str)      # 收尾结果说明
    done = Signal()

    def __init__(self, auto_launch=True, auto_close=True, parent=None):
        QThread.__init__(self, parent)
        self.auto_launch = auto_launch
        self.auto_close = auto_close
        self._cancel = False

    def stop(self):
        self._cancel = True

    def run(self):
        try:
            self.status.emit('正在检查模拟器与 App 授权…')
            manager = xqd_auth.find_mumu_manager()

            # ① 安卓设备
            #    注意：`control launch` 会把 MuMu 主程序连带带起来，
            #    所以不必（也不该）先单独 main launch —— 实测那样会卡住。
            if not xqd_auth.is_running(manager):
                if not self.auto_launch:
                    self.failed.emit(
                        'MuMu / 安卓设备未运行。请启动 MuMu 并在兴趣岛 App '
                        '中登录，然后回到这里点「重试」。')
                    return
                ok_dev, _launched = xqd_auth.ensure_device(
                    manager, on_status=self.status.emit)
                if not ok_dev:
                    self.failed.emit('安卓设备启动超时（240 秒）。')
                    return
            else:
                self.status.emit('安卓设备已在运行')

            # ② 读授权
            self.status.emit('读取 App 授权…')
            try:
                header = xqd_auth.get_cookie_header(manager)
            except xqd_auth.AuthError:
                self.status.emit('未检测到登录态，正在打开兴趣岛 App…')
                xqd_auth.launch_app(manager)
                # 此时**不能**关闭设备 —— 用户还要在里面登录
                self.failed.emit(
                    '兴趣岛 App 尚未登录。\n\n'
                    '已在模拟器中打开兴趣岛 App，请在模拟器窗口里完成登录，'
                    '然后回到本工具点「重试」。')
                return

            self.status.emit('授权获取成功')
            self.ok.emit(header)

            # ④ 收尾：关掉本工具启动的东西
            #    用会话状态判断 —— 即便这次 MuMu 早就在跑（用户刚登录完
            #    点「重试」），只要是本工具启动的，一样关掉。
            if self.auto_close:
                st = xqd_auth.session_state()
                if st['main'] or st['device']:
                    self.status.emit('正在关闭模拟器…')
                    try:
                        xqd_auth.close_all(manager)
                        self.closed.emit('已自动关闭 MuMu 模拟器与兴趣岛 App。')
                    except Exception as e:
                        self.closed.emit('关闭模拟器时出错：%s（不影响使用）' % e)
                else:
                    self.closed.emit('模拟器是您自己启动的，未自动关闭；'
                                     '工具已可独立运行，随时可以手动关掉。')
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            self.done.emit()


# ══════════════════════════════════════════════════════════════
#  下载工作线程
# ══════════════════════════════════════════════════════════════

class SpeedMeter(object):
    """速率计：按**滑动窗口**算速率。

    ★ 为什么不用「全程平均速度」：
      网络速度是波动的（CDN 节点切换、并发分片时快时慢）。
      用全程平均算 ETA，会在下载刚开始时严重偏大（那时候平均速度被
      启动开销拉低），而且速度变化后要等很久才反应过来。
      这里只取**最近几秒**的样本算速率，ETA 才会跟着实际速度变化。

    ★ 它测的是「任意单调递增量」的速率 —— 喂字节就得到 B/s，
      喂内容秒数就得到「倍速」。喂什么由调用方决定。

    样本点：每次收到进度回调时记 (时刻, 累计值)。
    """

    def __init__(self, window=8.0):
        self.window = window          # 速率统计窗口（秒）
        self.samples = []              # [(t, value)]
        self.last = 0                 # 最近一次累计值
        self.last_speed = 0.0         # ★ 最近一次**有效**速率（暂停后仍保留）
        self._origin = None           # 首个样本的时刻（作为相对时间原点）

    def reset(self, nbytes=0):
        self.samples = []
        self.last = nbytes
        self.last_speed = 0.0
        self._origin = None

    def add(self, nbytes, now=None):
        now = time.time() if now is None else now
        self.last = nbytes
        if self._origin is None:
            self._origin = now
        self.samples.append((now, nbytes))
        # 剪掉窗口外的旧样本（至少留 2 个，否则算不出速率）
        cut = now - self.window
        while len(self.samples) > 2 and self.samples[0][0] < cut:
            self.samples.pop(0)
        sp = self._calc_speed(now)
        if sp > 0:
            self.last_speed = sp

    def _calc_speed(self, now):
        if len(self.samples) < 2:
            return 0.0
        # ★ 数据过期（长时间没有新进度，例如卡在封装/校验阶段）
        #   就不要再报速率了，否则会显示一个假的「还在很快地下」。
        if now - self.samples[-1][0] > 6.0:
            return 0.0
        (t0, b0), (t1, b1) = self.samples[0], self.samples[-1]
        dt = t1 - t0
        if dt <= 0.2:
            return 0.0
        return max(0.0, (b1 - b0) / dt)

    def speed(self, now=None):
        """当前速率。样本不足或数据过期时返回 0。"""
        if now is None:
            now = time.time()
        return self._calc_speed(now)


# Z 盘（网络盘）实测写入速度约 10 MB/s，用来估算「封装」阶段还要多久
MUX_DISK_SPEED = 10.0 * 1024 * 1024


def fmt_dur(sec):
    """秒 -> 天:时:分:秒（按需省略前导单位）。

    显示规则（用户要求）：
        只有秒      -> 45           （不显示「分:」）
        只到分      -> 1:30         （不显示「时:」）
        只到时      -> 2:15:30      （不显示「天」）
        到天        -> 1:02:15:30

    最高位段不补零，其余各段一律两位（秒/分/时）。
    """
    if sec is None or sec < 0:
        return '--'
    sec = int(round(sec))
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return '%d:%02d:%02d:%02d' % (d, h, m, s)
    if h:
        return '%d:%02d:%02d' % (h, m, s)
    if m:
        return '%d:%02d' % (m, s)
    # ★ 只有秒 —— 不再带「分:」
    return '%d' % s


def fmt_speed(bps):
    """速率 → 紧凑字符串（列宽紧张，不带空格）。"""
    if not bps or bps <= 0:
        return '--'
    if bps < 1024:
        return '%dB/s' % bps
    if bps < 1024 * 1024:
        return '%dKB/s' % (bps / 1024.0)
    return '%.1fMB/s' % (bps / 1048576.0)


# ══════════════════════════════════════════════════════════════
#  「帮助」菜单：使用说明 + 关于与致谢
# ══════════════════════════════════════════════════════════════

HELP_HTML = """
<h3>使用说明</h3>

<p><b>1. 授权（平时不用开模拟器）</b><br>
顶栏显示「授权：…」。<b>平时启动工具直接使用本机保存的授权</b>，
不会拉起 MuMu 模拟器，也不必等它启动 / 关闭。<br>
只有<b>首次使用</b>（本机还没保存过授权），或你点顶栏<b>「重新授权」</b>时，
才会拉起 MuMu 与安卓设备，从兴趣岛 App 的 WebView 读取登录凭据
（rsessionId / userId），读完自动关闭模拟器并把新凭据保存到本机。<br>
授权过期、营列表加载不出来时，点一次「重新授权」即可刷新。<br>
凭据只存在本机私有文件 <code>%USERPROFILE%\\.xqd_tool\\cookie.txt</code>
（不在程序目录、不进仓库），也可用环境变量 <code>XQD_COOKIE</code> 临时覆盖。<br>
若显示「未登录」，请先在模拟器里打开兴趣岛并登录，再点「重新授权」。</p>

<p><b>2. 选择营</b><br>
左栏「营列表」列出你已订阅的营。用右上角下拉框切换「正式营 / 体验营」。<br>
<b>点营名前面的方框可勾选多个营</b>，标题栏的「全选」可一次勾上全部；
勾选的营，其课程会<b>合并进右侧同一张课程列表</b>，每节课仍存到自己营的
同名文件夹里。多个营名在标题里用「·」分隔并<b>向左循环滚动</b>
（鼠标悬停可看完整名单）。<br>
不勾任何营时，仍按老办法显示当前高亮的那一个营。</p>

<p><b>3. 勾选课程</b><br>
「课程列表」第一列「标题前缀」是该课在<b>原营</b>课表里的序号 ——
多营合并也不会重新编号，和成品文件名的前缀完全对应；
「标题后缀」列是成品文件名里的日期。<br>
「进度」列显示的是这节课<b>实际的下载进度</b>：已下完 100%，
没下完按下载历史 / 可续传的分片缓存显示百分比，正在下载的任务实时刷新，
重新载入课表也不会变空。<br>
勾选要下载的课；点表头左侧的方框可全选 / 全不选，也可用「全选」「清空」按钮。<br>
已完整下载过的课会自动标记并跳过（不重复消耗流量）；
残缺文件会被清除并用规范名重下。</p>

<p><b>4. 选择保存目录</b><br>
顶栏「下载目录」指定保存位置。<b>首次使用默认指向 Windows 的「下载」文件夹</b>
（<code>%USERPROFILE%\\Downloads</code>，跟随系统的文档重定向）；
你手动改过之后，工具会一直沿用你<b>最后一次修改的目录</b>。
改动方式：直接改输入框后按回车，或点「浏览…」选择。</p>

<p><b>5. 开始下载</b><br>
点「下载选中」批量下载，或选中某一课点「下载此课」。
「下载管理」表实时显示状态、已下/总量、速度、剩余时间；
点橙色「暂停」可暂停全部任务（已下好的分片会保留，
点「继续」从断点接着下，不重下）。</p>

<p><b>5.1 三处状态一一对应</b><br>
同一节课的状态显示在三个地方，用的是<b>同一套词</b>：<br>
① 课程列表里<b>跟在课名后面的方括号</b>（如 <code>清晰目标：开启性命双修之旅 [下载中]</code>）<br>
② 「下载管理」表的「状态」列<br>
③ 运行日志（<code>封装中：某某课</code> 这种）<br>
阶段词：<code>解析中</code>（解析清单）→ <code>下载中</code>（下分片）→
<code>封装中</code>（转封装 MP4）→ <code>校验中</code>（校验时长）→ <code>已完成</code>。<br>
其余状态：<code>已存在</code>（目录里已有成品）、
<code>排队中</code>、<code>已暂停</code>、<code>失败</code>、<code>需重下</code>。</p>

<p><b>5.2 「标题前缀 / 标题后缀」列是什么</b><br>
「标题前缀」= 该课在<b>原营</b>课表里的序号（1、2、3…），多营合并不重排；<br>
「标题后缀」= <b>成品文件名里标题后面那段日期</b> ——
文件名规则是 <code>&lt;序号&gt;.&lt;课名&gt;.&lt;YYYY.MM.DD&gt;.mp4</code>，
所以这一列就是那个 <code>YYYY.MM.DD</code>，
例如 <code>1.【复训营课程1】养正十三式复习.2026.04.18.mp4</code>
对应这一列显示 <code>2026.04.18</code>。
它和实际落盘的文件名同源，可以拿它核对文件。</p>

<p><b>5.3 进入封装时自动接上下一节</b><br>
一节分片下完、状态变成「封装中」之后，就<b>不再需要网络</b>了 ——
拼接分片、转封装 MP4、校验时长都只读写本地磁盘。工具会在这一刻
<b>把网络让给队列里的下一节</b>，不必等封装结束，带宽不空转。<br>
因此最多会有 3 节课同时下载、另有最多 2 节在封装；
限住封装路数是为了不抢网络盘（Z 盘）的写入带宽。
「下载管理」标题旁会显示 <code>N 下载 / M 封装</code> 的拆分。</p>

<p><b>6. 输出结构</b><br>
<code>&lt;营名&gt;\\&lt;序号&gt;.&lt;课名&gt;.&lt;YYYY.MM.DD&gt;.mp4</code><br>
例：<code>调和养正太极营\\7.徵火音养心21-23点【紫竹调】.2025.03.12.mp4</code><br>
视频统一转封装为 MP4；音频课保留原始音频格式（.mp3 / .m4a / .aac）。</p>

<p><b>提示</b><br>
「清除列表」只清任务表与历史记录，不动已下载的文件；
「删除文件」会把对应成品移走。两者都不影响已下载的内容本身。</p>

<p><b>7. 下载历史（跨会话记忆）</b><br>
「下载管理」里的任务列表和下载进度会被记住 —— <b>关掉工具再打开，
上次下过什么、下到哪了都还在</b>。<br>
未完成的课会标成「未完成（可续传）」：重新在课程列表里勾选它，
工具会直接接着上次的位置继续下（已下的分片还在缓存里，不会重下）。<br>
进度信息保存在 <code>%USERPROFILE%\\.xqd_tool\\history.json</code>，
分片缓存保存在同目录的 <code>parts\\</code> 下。</p>
"""

ABOUT_HTML = """
<h3>关于本工具</h3>
<p><b>兴趣岛视频下载器</b> v%s<br>
把「兴趣岛」App（<code>com.qlchat.xingqudao</code>）里你已付费订阅的
课程视频批量导出为通用 MP4，便于在教学大屏上直接播放。</p>

<p>本工具是<b>独立编写</b>的：兴趣岛的业务接口契约来自官方前端
JavaScript bundle 的明文；下载内核（分片并行、断点续下、拼接转封装）
为自行实现，不含任何账号体系或商业代码。</p>

<h3>参考与引用的开源项目</h3>
<table cellpadding="4">
<tr><td><b>学无止下载器</b><br>
<a href="https://github.com/Xue-Wu-Zhi/xuewuzhi-downloader">
github.com/Xue-Wu-Zhi/xuewuzhi-downloader</a></td>
<td>MIT License。参考其公开的平台目录与文档，
了解各教学平台的接口形态与常见加密方式。</td></tr>

<tr><td><b>PySide6 / Qt for Python</b></td>
<td>LGPL-3.0。界面框架。</td></tr>

<tr><td><b>FFmpeg</b></td>
<td>LGPL-2.1+ / GPL（视构建而定）。用于把 HLS 分片拼接转封装为 MP4，
并用 ffprobe 校验成品时长。</td></tr>

<tr><td><b>pycryptodome</b></td>
<td>BSD-2-Clause / Public Domain。用于网易云课堂(163)视频地址的
AES 解密内核。</td></tr>
</table>

<h3>特别声明</h3>
<p>在摸清兴趣岛与网易云课堂的接口细节时，曾分析学无止下载器官方
Windows 客户端（V1.5.0 / V2.19.70）的行为。本仓库中
<code>_lel/core/netease_mooc.py</code>（网易课堂 163 视频地址解密）
系依据其 V1.5.0 <code>Source/core</code> 的逻辑<b>独立复现</b>；
<code>_lel/login/</code>、<code>_lel/v2/</code> 为分析过程的记录。</p>
<p>上述部分<b>不属于</b> <code>Xue-Wu-Zhi/xuewuzhi-downloader</code>
仓库的 MIT 授权范围（该仓库仅公开文档与 Python 离线骨架，
官方客户端不在其源码授权内）。本工具不含其客户端代码，
仅用于个人学习与本地教学演示。</p>

<p>使用者请遵守课程提供方的授权要求，只处理自己有权访问与保存的内容。
本工具不提供、也不鼓励用于未购内容的批量获取。</p>
""" % APP_VERSION


# ★ 合并后的「使用说明与关于」——上半部分是用法，往下拉是关于与致谢。
HELP_ABOUT_HTML = (
    HELP_HTML
    + '\n<hr style="margin:14px 0;">\n'
    + ABOUT_HTML)


# ══════════════════════════════════════════════════════════════
#  下载工作线程
# ══════════════════════════════════════════════════════════════

class DownloadWorker(QThread):
    """下载一节课。

    ★ 对外只暴露一个**完成信号** `completed`（成功和失败都从这里出），
    外加 `progress` 进度信号。调用方不需要分别连 success/fail 两个槽，
    也不会漏掉某一路 —— 少一个分支就少一次「状态没更新」的坑。
    """

    progress = Signal(int, int, int, float, float)
    #                    job_id, 已下载字节, 总字节, 已下载时长, 总时长
    completed = Signal(int, bool, str, str)   # job_id, ok, message, out_path
    phase = Signal(int, str)                # job_id, 阶段名
    log = Signal(str)

    def __init__(self, platform, camp, lesson, out_path, quality, job_id,
                 control=None, seg_dir=None, parent=None):
        QThread.__init__(self, parent)
        self.platform = platform
        self.camp = camp
        self.lesson = lesson
        self.out_path = out_path
        self.quality = quality
        self.job_id = job_id
        # ★ 共享的暂停控制器（None = 不支持暂停）
        self.control = control
        # ★ 分片缓存目录（跨进程续传用）—— 同一节课的目录恒定，
        #   第二次打开工具再下同一节时，已下分片会被直接跳过。
        self.seg_dir = seg_dir

    def run(self):
        ok = False
        msg = ''
        final_path = self.out_path
        try:
            self.log.emit('开始下载：%s' % self.lesson.title)

            def on_progress(down, total, done_dur, total_dur):
                # ★ 把**字节数 + 时长**一起传出去：
                #   光有百分比算不出速率，也就算不出「还剩多久」。
                self.progress.emit(self.job_id, int(down), int(total),
                                   float(done_dur), float(total_dur))

            def on_phase(name):
                self.phase.emit(self.job_id, name)

            ok, msg, final_path = xqd_engine.download_lesson(
                lambda: self.platform.resolve(self.camp, self.lesson),
                self.out_path,
                quality=self.quality,
                workers=SEGMENT_WORKERS,
                on_progress=on_progress,
                expect_duration=self.lesson.duration,
                control=self.control,
                on_phase=on_phase,
                seg_dir=self.seg_dir)
        except Exception as e:
            ok = False
            msg = '%s' % e
        finally:
            # ★ 无论成功失败，都从这一个信号出去
            self.completed.emit(self.job_id, ok, msg, final_path)


# ══════════════════════════════════════════════════════════════
#  主窗口
# ══════════════════════════════════════════════════════════════

class ScanWorker(QThread):
    """后台扫描下载目录，标出哪些课已经下过了。

    为什么要后台：ffprobe 一次约 100ms，一个营最多 70 节，
    在 UI 线程里做会卡住界面 7 秒。

    ★★ 结果必须按 **lesson 身份** 回传，不能按「行号」。
    行号只在「当前显示的这张表」里才有意义 —— 用户切营后表格会重建，
    行号含义就变了。旧扫描线程这时再按旧行号回传，会把**新营**的行
    标成旧营的判定结果（表现为「没下过的课自动变成已下载」）。
    这里用 lesson 对象本身当键，回传时直接带 lesson 引用，
    主窗口按引用比对，天然免疫切营错位。
    """

    done = Signal(object)     # list of (lesson, ok, state)
    finished_all = Signal()

    def __init__(self, checker, folder=None, lessons=None, alt_folders=None,
                 groups=None, parent=None):
        QThread.__init__(self, parent)
        self.checker = checker
        # ★ v1.5.0：多营合并时每个营有自己的输出目录，扫描要按营分组。
        #   groups = [(folder, lessons, alt_folders), ...]；
        #   旧的单营调用 (checker, folder, lessons, alt) 仍然兼容。
        self.groups = groups or [(folder, lessons, alt_folders or [])]
        self.result = []

    def run(self):
        try:
            n = 0
            for folder, lessons, alt in self.groups:
                for le in (lessons or []):
                    stem = xqd_platform.lesson_stem(le)
                    st = self.checker.check_group(folder, stem, le.duration,
                                                  alt_folders=alt)
                    if st['status'] != 'missing':
                        self.result.append((le, st['status'] == 'ok', st))
                    # 每 10 节发一次，避免一次构造大 list
                    n += 1
                    if n % 10 == 9:
                        self.done.emit(list(self.result))
            self.done.emit(list(self.result))
        except Exception:
            pass
        finally:
            self.finished_all.emit()


class CatalogWorker(QThread):
    """后台批量拉「多个营」的课表（v1.5.0 营多选）。

    ★ 为什么必须后台：全选 9 个营最多要 9 次网关请求，网络不稳时
      一次可能十几秒；放 UI 线程会把窗口整个冻住。
    ★ 为什么逐营 emit：边加载边往课程表里追加，用户不必等全部完成。
    ★ ``gen`` 是作废标记：用户改了勾选后，上一批线程的结果必须丢弃，
      否则会把旧营的课混进新表格。
    ★ 课表本身由 platform._catalogs 缓存，重复勾选不会重复发请求。
    """

    loaded = Signal(int, object, object)   # gen, camp, lessons
    failed = Signal(int, object, str)      # gen, camp, 原因
    finished_all = Signal(int)             # gen

    def __init__(self, platform, camps, gen, parent=None):
        QThread.__init__(self, parent)
        self.platform = platform
        self.camps = list(camps)
        self.gen = gen

    def run(self):
        for camp in self.camps:
            try:
                cat = list(self.platform.camp_catalog(camp) or [])
            except Exception as e:
                self.failed.emit(self.gen, camp, str(e))
                continue
            self.loaded.emit(self.gen, camp, cat)
        self.finished_all.emit(self.gen)


class HtmlDialog(QDialog):
    """显示一段 HTML 的只读对话框（用于「使用说明」与「关于」）。"""

    def __init__(self, title, html, parent=None, width=660, height=560):
        QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self.resize(width, height)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        self.view = QTextBrowser(self)
        self.view.setOpenExternalLinks(True)
        self.view.setHtml(html)
        self.view.setStyleSheet(
            'QTextBrowser { background: #ffffff; border: 1px solid #d3dae6;'
            ' border-radius: 6px; padding: 8px; }')
        lay.addWidget(self.view, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton('关闭')
        btn.clicked.connect(self.accept)
        btn.setDefault(True)
        row.addWidget(btn)
        lay.addLayout(row)


class ClickOverlay(QWidget):
    """透明点击层。

    ★ 盖在别的控件**上方**，视觉上完全透明（不画背景、不加边框），
      但能接住鼠标点击 —— 用来做「隐形热区」：
      既不做成按钮，也不做成链接，点哪都行。
    """

    clicked = Signal()

    def __init__(self, parent=None, tip=''):
        QWidget.__init__(self, parent)
        # 不自动填背景 → 父控件的蓝色渐变照样透出来
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_StyledBackground, False)
        # 鼠标指针给个手型，暗示这里可点（但不做成按钮样式）
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        QWidget.mousePressEvent(self, e)


class BrandBox(QWidget):
    """顶栏左侧的品牌区（主标题 + 副标题）。

    ★ 整块区域被一个透明点击层盖住 —— 点标题或副标题都弹
      「使用说明与关于」对话框，不再占用顶栏以外的任何空间。
    """

    clicked = Signal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        t1 = QLabel('兴趣岛视频下载器')
        t1.setObjectName('Brand')
        t2 = QLabel('批量导出课程视频为通用 MP4')
        t2.setObjectName('BrandSub')
        lay.addWidget(t1)
        lay.addWidget(t2)

        self.overlay = ClickOverlay(self, '点击查看使用说明与关于本工具')
        self.overlay.clicked.connect(self.clicked)
        self.overlay.raise_()

    def resizeEvent(self, e):
        # 让点击层始终铺满整个品牌区
        self.overlay.setGeometry(self.rect())
        QWidget.resizeEvent(self, e)

    def enterEvent(self, e):
        self.overlay.raise_()
        QWidget.enterEvent(self, e)


class MainWindow(QMainWindow):

    log_msg = Signal(str)

    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle('%s  v%s' % (APP_TITLE, APP_VERSION))
        self.resize(1220, 800)
        self.setMinimumSize(980, 640)

        self.cfg = load_config()
        # ★ 下载目录的记忆规则（用户要求）：
        #     第一次使用 → 指向 Windows 的「下载」文件夹；
        #     用户改过之后 → 一直沿用他最后改的那个目录。
        #
        #   config.json 里的 out_dir 就是「用户最后用的目录」，
        #   改目录时会自动存进去（见 _save_cfg），所以这里直接读。
        #
        #   边界：老版本把默认值 Z:\太极营 也写进了 config。
        #   若那个目录在本机不存在（换机器 / 换了盘），就不能再用它，
        #   改回 Windows 的「下载」文件夹。
        cfg_dir = (self.cfg.get('out_dir') or '').strip()
        legacy = [d.replace('/', chr(92)).rstrip(chr(92))
                  for d in _LEGACY_OUT_DIRS]
        if cfg_dir and os.path.isdir(cfg_dir):
            self.out_dir = cfg_dir
        elif cfg_dir and cfg_dir.replace('/', chr(92)).rstrip(chr(92)) in legacy:
            # 旧默认目录，但本机没有 → 回到 Windows 的「下载」文件夹
            self.out_dir = default_out_dir()
        elif cfg_dir:
            # 用户自定的目录暂时不可用（盘没挂上）→ 仍然记住它，
            # 不要偷偷改成别处。
            self.out_dir = cfg_dir
        else:
            self.out_dir = default_out_dir()
        self.quality = self.cfg.get('quality') or 'max'
        self.platform_id = self.cfg.get('platform') or 'qianliao'

        # ★ 下载历史（下载列表 + 下载进度）—— 第二次打开工具时恢复
        self.history = xqd_history.load_history()
        # 历史落盘的节流时间戳（_on_progress 里用）
        self._hist_last_flush = 0.0

        self.cookie = ''
        self.platform = None
        self.auth_worker = None
        self.current_camp = None
        self.camps = []
        self.lessons = []
        self.row_of_lesson = {}     # lesson -> row
        self.lesson_of_row = {}     # row -> lesson
        # ★ v1.5.0：多营合并后行号不再是「营内序号」，每行都要记住自己
        #   属于哪个营（输出目录、已下载检测、下载任务都按这个营算）。
        self.camp_of_row = {}       # row -> Camp
        self._lesson_groups = []    # 当前表格内容：[(camp, lessons), ...]
        self._checked_lesson_keys = set()   # 重建表格时保留课程勾选
        self._camp_updating = False         # 防止营勾选联动递归
        self._rebuild_scheduled = False     # 勾选事件的防抖标志
        self._catalog_gen = 0               # 旧课表加载线程的作废标记
        self._catalog_workers = []          # ★ QThread 运行期间必须保活
        self._camp_target = []              # 本次要显示的营（用于判重）
        self.active_threads = []
        self.pending_queue = []      # 待下载：(job_id, lesson, camp, out_path, quality)
        self.running_workers = set()  # 所有在跑的 job_id（含封装/校验）
        # ★ 已进入本地阶段、把网络槽位还回去的 job_id。
        #   running_workers - network_released = 真正占着带宽的任务。
        #   见文件头 LOCAL_PHASES / MAX_MUX_WORKERS 的说明。
        self.network_released = set()
        self.jobs = {}               # job_id -> dict(row, lesson, camp, out_path)
        self._task_row_of_job = {}    # job_id -> 下载管理表里的行号
        self._job_seq = 0
        self.checker = xqd_dedupe.ExistingChecker(self.out_dir)
        self.scan_worker = None
        # ★ 保活列表：运行中的 ScanWorker 绝不能被 GC 析构。
        #   QThread 在运行中被销毁会让 Qt 直接 abort（进程无异常信息地消失）。
        #   见 _scan_existing 的注释。
        self._scan_workers = []
        self._scan_counts = (0, 0)
        # ★ 全局暂停控制器 —— 所有下载线程共用一个
        self.control = xqd_engine.DownloadControl()
        self._paused = False

        self._build_ui()
        self._apply_style()
        self._load_platform()

        # ★ 恢复上次的下载列表（用户要求：第二次打开工具仍能看到
        #   下载过什么、下到哪了）。放在 _build_ui 之后 —— 表要先建好。
        self._restore_history_tasks()
        # ★ 顺手清掉「孤儿」分片缓存（历史里已是终态的残留）。
        #   未完成的分片要留着 —— 那是续传的本钱。
        try:
            n, freed = xqd_history.purge_orphan_parts(self.history)
            if n:
                self.log('清理残留分片缓存：%d 个目录，%.1f MB'
                         % (n, freed / 1048576.0))
        except Exception as e:
            self.log('清理分片缓存失败：%s' % e)

        # ★ 每秒刷新一次剩余时间 —— 让倒计时「走字」，
        #   也让「封装」阶段的估算值能随时间收敛。
        self._eta_timer = QTimer(self)
        self._eta_timer.setInterval(1000)
        self._eta_timer.timeout.connect(self._tick_eta)
        self._eta_timer.start()

        # ★ 自检/取证模式（XQD_SCREENSHOT）只为看界面渲染，别为了截个图
        #   就把 MuMu 模拟器拉起来 —— 那会连带启动安卓设备、改系统状态。
        #   正常启动仍自动检查授权（优先用本机保存的，不碰模拟器）。
        if not os.environ.get('XQD_SCREENSHOT'):
            QTimer.singleShot(300, self.auto_check_auth)

    def _tick_eta(self):
        """定时刷新剩余时间估算。"""
        if not self.running_workers and not self.pending_queue:
            if self.lbl_task_eta.text():
                self.lbl_task_eta.setText('')
            return
        # ★ 暂停时**冻结**估算值：速率会归零，不冻结的话倒计时会
        #   突然跳成「--」，看着像任务丢了。
        if not (self.control is not None and self.control.is_paused()):
            for job_id in list(self.running_workers):
                job = self.jobs.get(job_id)
                if not job:
                    continue
                # ★ 字节速率（显示用）
                bmeter = job.get('bmeter')
                if bmeter is not None:
                    job['speed'] = bmeter.speed()
                # ★ 内容速率（ETA 用）
                if (job.get('unit') or 'dur') == 'dur':
                    meter = job.get('meter')
                    if meter is not None:
                        job['rate_dur'] = meter.speed()
                else:
                    job['rate_dur'] = job.get('speed') or 0.0
                job['eta'] = self._compute_eta(job)
        self._refresh_all_task_rows()
        self._update_global_eta()

    # ── UI 构建 ────────────────────────────────────────────
    def _build_ui(self):
        # QMainWindow：顶栏与内容分离
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 10)
        body_layout.setSpacing(10)

        # 授权提示条
        self.banner = QLabel('')
        self.banner.setObjectName('Banner')
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        body_layout.addWidget(self.banner)

        # 横向分栏：左 = 营列表（**全高**），右 = 课程表 + 下载管理 + 运行日志
        # （下半区整体右移，与课程列表左对齐，不再横跨整个窗口）
        outer = QSplitter(Qt.Horizontal)
        outer.addWidget(self._build_camp_panel())
        outer.addWidget(self._build_right_column())
        outer.setStretchFactor(0, 0)
        outer.setStretchFactor(1, 1)
        outer.setCollapsible(0, False)
        outer.setSizes([300, 900])
        body_layout.addWidget(outer, 1)

        root.addWidget(body, 1)

        self.setCentralWidget(central)

        # 状态栏
        self.status_label = QLabel('就绪')
        self.statusBar().addWidget(self.status_label)
        self.statusBar().addPermanentWidget(
            QLabel('兴趣岛 · %s' % APP_VERSION))

        # ★ 不用菜单栏：品牌区的透明点击层直接弹「使用说明与关于」
        self._build_brand_actions()

    def _build_brand_actions(self):
        """全局快捷键（不占用任何界面空间）。

        ★ 顶部不再有「帮助」菜单栏 —— 品牌标题区本身就是点击入口。
        """
        act_quit = QAction('退出', self)
        act_quit.setShortcut('Ctrl+Q')
        act_quit.triggered.connect(self.close)
        self.addAction(act_quit)

    def show_help_about(self):
        """「使用说明与关于」对话框（上半是用法，下半是关于与致谢）。"""
        dlg = HtmlDialog('使用说明与关于', HELP_ABOUT_HTML, self,
                         width=700, height=640)
        dlg.exec()

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName('TopBar')
        bar.setFixedHeight(62)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 8, 18, 8)
        lay.setSpacing(12)

        brand = BrandBox(bar)
        brand.clicked.connect(self.show_help_about)
        lay.addWidget(brand)
        lay.addSpacing(20)

        lay.addWidget(QLabel('平台'))
        self.cmb_platform = QComboBox()
        for pid, cls in xqd_platform.REGISTRY.items():
            self.cmb_platform.addItem(cls.display_name, pid)
        self.cmb_platform.setCurrentIndex(
            max(0, self.cmb_platform.findData(self.platform_id)))
        self.cmb_platform.currentIndexChanged.connect(self._on_platform_changed)
        lay.addWidget(self.cmb_platform)

        lay.addSpacing(14)
        lay.addWidget(QLabel('下载目录'))
        self.ed_out = QLineEdit(self.out_dir)
        self.ed_out.setMinimumWidth(280)
        # ★ 用户直接改输入框也要被记住（不点「浏览…」也要生效）
        self.ed_out.editingFinished.connect(self._save_cfg)
        lay.addWidget(self.ed_out)

        self.btn_browse = QPushButton('浏览…')
        self.btn_browse.clicked.connect(self._on_browse)
        lay.addWidget(self.btn_browse)

        lay.addStretch(1)

        # 自动启停模拟器（授权链路用）
        self.chk_autolaunch = QCheckBox('自动启动 MuMu')
        self.chk_autolaunch.setChecked(True)
        self.chk_autolaunch.setToolTip(
            '仅在「本机还没有保存授权」或点「重新授权」时才生效：\n'
            '未运行 MuMu / 安卓设备时，自动拉起它们以获取授权。\n'
            '平时启动工具直接用已保存的授权，不会启动模拟器。')
        lay.addWidget(self.chk_autolaunch)

        self.chk_autoclose = QCheckBox('授权后自动关闭')
        self.chk_autoclose.setChecked(True)
        self.chk_autoclose.setToolTip(
            '仅在真正走了模拟器授权时生效：\n'
            '拿到授权后自动关闭兴趣岛 App 与安卓设备（省内存）')
        lay.addWidget(self.chk_autoclose)

        self.lbl_auth = QLabel('授权：检查中…')
        self.lbl_auth.setObjectName('BrandSub')
        lay.addWidget(self.lbl_auth)

        self.btn_retry = QPushButton('重新授权')
        self.btn_retry.setToolTip(
            '从 MuMu 模拟器重新读取兴趣岛登录态，并刷新本机保存的授权。\n'
            '平时启动工具直接用已保存的授权，不会启动模拟器。')
        # ★ 点按钮 = 强制走模拟器刷新。不能沿用缓存，否则 Cookie 过期时
        #   永远刷不掉（缓存分支只在自动检查时生效）。
        self.btn_retry.clicked.connect(
            lambda _checked=False: self.auto_check_auth(force_mumu=True))
        lay.addWidget(self.btn_retry)

        return bar

    def _build_right_column(self):
        """右列：课程列表（上） + 下载管理（中） + 运行日志（下）。

        三者用**同一个纵向 QSplitter**，但下载管理与日志的容器都设了
        maximumHeight，保证课程表拿到大部分空间（课程表是主工作区）。
        """
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.tbl_lessons_host = self._build_lesson_panel()

        task_host = QWidget()
        task_host.setMaximumHeight(240)
        tl = QVBoxLayout(task_host)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self._build_task_panel())

        log_host = QWidget()
        log_host.setMaximumHeight(210)
        ll = QVBoxLayout(log_host)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self._build_log_panel())

        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.addWidget(self.tbl_lessons_host)
        self.right_splitter.addWidget(task_host)
        self.right_splitter.addWidget(log_host)
        self.right_splitter.setStretchFactor(0, 1)
        self.right_splitter.setStretchFactor(1, 0)
        self.right_splitter.setStretchFactor(2, 0)
        self.right_splitter.setCollapsible(1, True)
        self.right_splitter.setCollapsible(2, True)
        # 初始比例：课程表占大头。stretchFactor 只在窗口缩放时生效，
        # 初始尺寸必须用 setSizes 显式给（否则三块会被均分）。
        self.right_splitter.setSizes([620, 190, 150])
        lay.addWidget(self.right_splitter, 1)
        return col

    def _build_camp_panel(self):
        card = QFrame()
        card.setObjectName('Card')
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel('营列表')
        title.setObjectName('SectionTitle')
        head.addWidget(title)
        head.addStretch(1)
        # ★ v1.5.0：营也能勾选 / 全选 —— 勾中的营，其课表全部并入课程列表
        self.chk_all_camps = QCheckBox('全选')
        self.chk_all_camps.setTristate(True)
        self.chk_all_camps.setToolTip(
            '勾选全部营，把它们的课程一起加进课程列表；再点一次取消全部')
        self.chk_all_camps.stateChanged.connect(self._on_all_camps_changed)
        head.addWidget(self.chk_all_camps)
        self.cmb_kind = QComboBox()
        head.addWidget(self.cmb_kind)
        lay.addLayout(head)

        self.lst_camps = QListWidget()
        self.lst_camps.setWordWrap(False)
        self.lst_camps.setSpacing(1)
        self.lst_camps.currentRowChanged.connect(self._on_camp_selected)
        self.lst_camps.itemChanged.connect(self._on_camp_item_changed)
        # ★ 点营名文字 = 勾上这个营（只增不减）；点前面的方框才是切换。
        #   两种点击都交给 _on_camp_clicked 按击中点区分。
        self.lst_camps.itemClicked.connect(self._on_camp_clicked)
        lay.addWidget(self.lst_camps, 1)

        row = QHBoxLayout()
        self.btn_refresh_camps = QPushButton('刷新')
        self.btn_refresh_camps.clicked.connect(self.load_camps)
        row.addWidget(self.btn_refresh_camps)
        self.lbl_camp_hint = QLabel('')
        self.lbl_camp_hint.setObjectName('Muted')
        row.addWidget(self.lbl_camp_hint, 1)
        lay.addLayout(row)

        return card

    def _build_lesson_panel(self):
        card = QFrame()
        card.setObjectName('Card')
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        fixed_title = QLabel('课程列表 ·')
        fixed_title.setObjectName('SectionTitle')
        head.addWidget(fixed_title)
        # ★ 多营时营名向左循环滚动（中文间隔号「·」分隔），单营静止
        self.lbl_lessons = MarqueeLabel()
        self.lbl_lessons.setObjectName('SectionTitle')
        head.addWidget(self.lbl_lessons)
        head.addStretch(1)

        self.cmb_quality = QComboBox()
        self.cmb_quality.addItem('最高画质 (1080p)', 'max')
        self.cmb_quality.addItem('省流量 (720p)', '720')
        self.cmb_quality.setCurrentIndex(
            max(0, self.cmb_quality.findData(self.quality)))
        self.cmb_quality.currentIndexChanged.connect(
            lambda: self._save_cfg())
        head.addWidget(self.cmb_quality)

        self.btn_all = QPushButton('全选')
        self.btn_all.clicked.connect(lambda: self._select_all(True))
        head.addWidget(self.btn_all)

        self.btn_none = QPushButton('清空')
        self.btn_none.clicked.connect(lambda: self._select_all(False))
        head.addWidget(self.btn_none)

        self.btn_rescan = QPushButton('重新检测')
        self.btn_rescan.setToolTip('重新扫描下载目录，标记哪些课已经下过了')
        self.btn_rescan.clicked.connect(self.rescan_existing)
        head.addWidget(self.btn_rescan)

        self.btn_dl = QPushButton('下载选中')
        self.btn_dl.setObjectName('Primary')
        self.btn_dl.clicked.connect(self.start_download_selected)
        head.addWidget(self.btn_dl)

        # ★ 暂停 / 继续 —— 暂停所有正在进行的下载
        self.btn_pause = QPushButton('暂停')
        self.btn_pause.setObjectName('PauseBtn')
        self.btn_pause.setToolTip('暂停所有正在进行的下载（已下好的分片会保留，'
                                  '点「继续」接着下）')
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.toggle_pause)
        head.addWidget(self.btn_pause)

        self.btn_dl_one = QPushButton('下载此课')
        self.btn_dl_one.setToolTip('只下载当前选中的一节课')
        self.btn_dl_one.clicked.connect(self._on_download_one_clicked)
        head.addWidget(self.btn_dl_one)

        lay.addLayout(head)

        self.tbl_lessons = QTableWidget(0, LESSON_COLUMN_COUNT)
        # ★ v1.5.0 列结构（用户 2026-11-07 要求）：
        #   第 1 列「标题前缀」= 该课在**原营**课表里的序号（成品文件名的
        #     `<序号>.` 前缀），多营合并时也**不重新编号**；
        #   第 2 列「课程」= 纯课名 + 紧跟课名的状态词（自绘委托）；
        #   第 3 列「标题后缀」= 成品文件名里标题后面那段日期
        #     （`1.【复训营课程1】养正十三式复习.2026.04.18.mp4` 里的
        #      `2026.04.18`），与实际落盘的文件名同源。
        self.tbl_lessons.setHorizontalHeaderLabels(
            ['', '标题前缀', '课程', '标题后缀', '时长', '进度'])
        self.hdr_lessons = CheckHeaderView(self.tbl_lessons)
        self.hdr_lessons.toggled.connect(self._on_header_toggled)
        self.tbl_lessons.setHorizontalHeader(self.hdr_lessons)
        self.tbl_lessons.verticalHeader().setVisible(False)
        self.tbl_lessons.setAlternatingRowColors(True)
        self.tbl_lessons.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_lessons.setEditTriggers(QTableWidget.NoEditTriggers)
        # ★ 状态词跟着课名走 → 用自绘委托，课名和状态词分别着色
        self.tbl_lessons.setItemDelegateForColumn(
            COL_TITLE, LessonTitleDelegate(self.tbl_lessons))
        hh = self.tbl_lessons.horizontalHeader()
        for c in (COL_CHECK, COL_PREFIX, COL_SUFFIX, COL_DUR, COL_PROGRESS):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
        hh.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        self.tbl_lessons.setColumnWidth(COL_CHECK, 34)
        self.tbl_lessons.setColumnWidth(COL_PREFIX, 74)
        self.tbl_lessons.setColumnWidth(COL_SUFFIX, 96)
        self.tbl_lessons.setColumnWidth(COL_DUR, 76)
        self.tbl_lessons.setColumnWidth(COL_PROGRESS, 150)
        self.tbl_lessons.verticalHeader().setDefaultSectionSize(26)
        self.tbl_lessons.cellDoubleClicked.connect(self._on_row_double_click)
        self.tbl_lessons.itemChanged.connect(self._on_lesson_item_changed)
        lay.addWidget(self.tbl_lessons, 1)

        # 已存在提示条
        self.lbl_exist = QLabel('')
        self.lbl_exist.setObjectName('Muted')
        lay.addWidget(self.lbl_exist)

        self.lbl_lesson_hint = QLabel('选择左侧营查看课程')
        self.lbl_lesson_hint.setObjectName('Muted')
        lay.addWidget(self.lbl_lesson_hint)

        return card

    def _build_task_panel(self):
        card = QFrame()
        card.setObjectName('Card')
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel('下载管理')
        title.setObjectName('SectionTitle')
        head.addWidget(title)
        # ★ 全局剩余时间汇总（所有在跑 + 排队任务加起来）
        self.lbl_task_eta = QLabel('')
        self.lbl_task_eta.setObjectName('BrandSub')
        head.addWidget(self.lbl_task_eta)
        head.addStretch(1)

        self.btn_clear_list = QPushButton('清除列表')
        self.btn_clear_list.clicked.connect(self.clear_task_list)
        head.addWidget(self.btn_clear_list)

        self.btn_delete_files = QPushButton('删除文件')
        self.btn_delete_files.setObjectName('Danger')
        self.btn_delete_files.clicked.connect(self.delete_task_files)
        head.addWidget(self.btn_delete_files)

        lay.addLayout(head)

        self.tbl_tasks = QTableWidget(0, 6)
        self.tbl_tasks.setHorizontalHeaderLabels(
            ['', '课程', '状态', '大小', '速度', '剩余时间'])
        self.hdr_tasks = CheckHeaderView(self.tbl_tasks)
        self.hdr_tasks.toggled.connect(self._on_task_header_toggled)
        self.tbl_tasks.setHorizontalHeader(self.hdr_tasks)
        self.tbl_tasks.verticalHeader().setVisible(False)
        self.tbl_tasks.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_tasks.setSelectionBehavior(QTableWidget.SelectRows)
        hh = self.tbl_tasks.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)
        hh.setSectionResizeMode(5, QHeaderView.Fixed)
        self.tbl_tasks.setColumnWidth(0, 34)
        self.tbl_tasks.setColumnWidth(2, 96)
        self.tbl_tasks.setColumnWidth(3, 112)
        self.tbl_tasks.setColumnWidth(4, 78)
        self.tbl_tasks.setColumnWidth(5, 88)
        self.tbl_tasks.verticalHeader().setDefaultSectionSize(26)
        self.tbl_tasks.itemChanged.connect(self._on_task_item_changed)
        lay.addWidget(self.tbl_tasks, 1)

        return card

    def _build_log_panel(self):
        card = QFrame()
        card.setObjectName('Card')
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel('运行日志')
        title.setObjectName('SectionTitle')
        head.addWidget(title)
        head.addStretch(1)
        btn = QPushButton('清空日志')
        btn.clicked.connect(lambda: self.txt_log.clear())
        head.addWidget(btn)
        lay.addLayout(head)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumBlockCount(2000)
        lay.addWidget(self.txt_log, 1)

        return card

    def _apply_style(self):
        self.setStyleSheet(QSS)

    # ── 平台 ───────────────────────────────────────────────
    def _on_platform_changed(self):
        self.platform_id = self.cmb_platform.currentData()
        self._load_platform()
        self._save_cfg()

    def _load_platform(self):
        try:
            self.platform = xqd_platform.create_platform(
                self.platform_id, self.cookie)
            self.cmb_kind.clear()
            for k in self.platform.camp_kinds:
                self.cmb_kind.addItem(k)
        except Exception as e:
            self.log('加载平台失败：%s' % e)
            self.platform = None

    # ── 授权 ───────────────────────────────────────────────
    def auto_check_auth(self, force_mumu=False):
        """授权入口。

        ★ v1.5.1 起默认**先用本机保存的授权**，一个 MuMuManager 都不调。
          只有两种情况才会启动模拟器：
            1. 本机没有保存过授权（首次使用）
            2. 用户点「重新授权」主动刷新（force_mumu=True）
          这样从根上避开「MuMu 的 Qt5 程序继承了本工具 Qt6 的
          QT_PLUGIN_PATH → 弹出 no Qt platform plugin could be initialized」。
          真要调用 MuMu 时，xqd_proc 也已做环境隔离（见该模块注释）。
        """
        if self.auth_worker and self.auth_worker.isRunning():
            return

        if not force_mumu:
            cached = ''
            try:
                cached = xqd_creds.load_cookie()
            except Exception:
                cached = ''
            if cached:
                self.cookie = cached
                if self.platform:
                    self.platform.cookie = cached
                self.lbl_auth.setText('授权：已就绪（本机保存）')
                self.banner.setObjectName('BannerOk')
                self.banner.setText(
                    '已使用本机保存的授权，未启动 MuMu 模拟器。'
                    '若授权过期，点右上「重新授权」刷新。')
                self.banner.setVisible(True)
                self.log('使用本机保存的授权（未启动模拟器）。')
                self.load_camps()
                return

        self.btn_retry.setEnabled(False)
        self.lbl_auth.setText('授权：检查中…')
        self.banner.setVisible(False)

        self.auth_worker = AuthWorker(
            auto_launch=self.chk_autolaunch.isChecked(),
            auto_close=self.chk_autoclose.isChecked())
        self.auth_worker.status.connect(self._on_auth_status)
        self.auth_worker.ok.connect(self._on_auth_ok)
        self.auth_worker.failed.connect(self._on_auth_failed)
        self.auth_worker.closed.connect(self._on_auth_closed)
        self.auth_worker.done.connect(
            lambda: self.btn_retry.setEnabled(True))
        self.auth_worker.start()

    def _on_auth_status(self, text):
        self.lbl_auth.setText('授权：%s' % text)
        self.log(text)

    def _on_auth_ok(self, cookie):
        self.cookie = cookie
        if self.platform:
            self.platform.cookie = cookie
        self.lbl_auth.setText('授权：已就绪')
        self.banner.setObjectName('BannerOk')
        self.banner.setText(
            '授权成功。工具已可独立运行，模拟器和 App 可以关闭。')
        self.banner.setVisible(True)
        # ★ 落盘供下次启动复用：之后启动完全不必再碰 MuMuManager。
        #   xqd_creds.save_cookie 自带测试隔离，不会覆盖真实凭据文件。
        saved = False
        try:
            saved = xqd_creds.save_cookie(cookie)
        except Exception:
            saved = False
        self.log('授权成功。' +
                 ('已保存到本机私有文件，下次启动无需模拟器。' if saved else ''))
        self.load_camps()

    def _on_auth_closed(self, text):
        self.log(text)
        if '自动关闭' in text:
            self.banner.setText('授权成功 —— %s' % text)
        else:
            self.banner.setText('授权成功 —— %s' % text)

    def _on_auth_failed(self, reason):
        self.lbl_auth.setText('授权：未就绪')
        self.banner.setObjectName('BannerErr')
        self.banner.setText(reason)
        self.banner.setVisible(True)
        self.log('授权未就绪：%s' % reason.splitlines()[0])

    # ── 营（v1.5.0：勾选 / 全选 / 多营合并）──────────────────
    def load_camps(self):
        if not self.platform:
            self.log('没有可用平台。')
            return
        if not self.cookie:
            self.log('尚未获得授权，无法加载营列表。')
            return
        kind = self.cmb_kind.currentText() or self.platform.camp_kinds[0]
        # ★ 刷新 / 切标签后，同名营的勾选状态要保留
        prev = set()
        for i in range(self.lst_camps.count()):
            it = self.lst_camps.item(i)
            if (it is not None and it.checkState() == Qt.Checked
                    and i < len(self.camps)):
                prev.add(getattr(self.camps[i], 'camp_id', '')
                         or getattr(self.camps[i], 'name', ''))
        self.lbl_camp_hint.setText('加载中…')
        self.log('加载%s列表…' % kind)
        try:
            camps = self.platform.list_camps(kind)
        except Exception as e:
            self.lbl_camp_hint.setText('加载失败')
            self.log('加载营列表失败：%s' % e)
            # ★ 用缓存授权时最常见的失败就是 Cookie 过期 ——
            #   明确告诉用户去哪刷新，别让他以为工具坏了。
            self.banner.setObjectName('BannerErr')
            self.banner.setText(
                '加载营列表失败，可能是本机保存的授权已过期或网络不稳定。'
                '请点右上「重新授权」从模拟器刷新。')
            self.banner.setVisible(True)
            return
        self.camps = camps
        self.lst_camps.blockSignals(True)
        self.lst_camps.clear()
        for c in camps:
            # 单行显示，避免两行文本被裁切
            item = QListWidgetItem('%s    %s' % (c.name, c.badge))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable
                          | Qt.ItemIsEnabled)
            key = getattr(c, 'camp_id', '') or c.name
            item.setCheckState(Qt.Checked if key in prev else Qt.Unchecked)
            item.setToolTip('%s（%s）\n点营名文字 = 加入课程列表；'
                            '点前面的方框 = 勾选 / 取消' % (c.name, c.badge))
            self.lst_camps.addItem(item)
        self.lst_camps.blockSignals(False)
        self._sync_all_camps_checkbox()
        self.log('%s：%d 个' % (kind, len(camps)))
        if camps:
            self.current_camp = camps[0]
            self.lst_camps.setCurrentRow(0)
            self._schedule_lesson_rebuild()

    # ── 营勾选 ─────────────────────────────────────────────
    def _checked_camps(self):
        """当前勾选的营（按营列表顺序）。"""
        out = []
        for i in range(self.lst_camps.count()):
            it = self.lst_camps.item(i)
            if (it is not None and it.checkState() == Qt.Checked
                    and i < len(self.camps)):
                out.append(self.camps[i])
        return out

    def _sync_all_camps_checkbox(self):
        """把「全选」复选框同步成三态，并更新左下角计数。"""
        n = self.lst_camps.count()
        k = len(self._checked_camps())
        if k == 0:
            st = Qt.Unchecked
        elif k == n and n > 0:
            st = Qt.Checked
        else:
            st = Qt.PartiallyChecked
        self.chk_all_camps.blockSignals(True)
        self.chk_all_camps.setCheckState(st)
        self.chk_all_camps.blockSignals(False)
        self.lbl_camp_hint.setText(
            '%d 个营%s' % (len(self.camps),
                          (' · 已勾选 %d 个' % k) if k else ''))

    def _on_all_camps_changed(self, state):
        """点「全选」→ 勾上全部营 / 取消全部营。"""
        if self._camp_updating:
            return
        want = state != Qt.Unchecked
        self._camp_updating = True
        self.lst_camps.blockSignals(True)
        for i in range(self.lst_camps.count()):
            self.lst_camps.item(i).setCheckState(
                Qt.Checked if want else Qt.Unchecked)
        self.lst_camps.blockSignals(False)
        self._camp_updating = False
        self._sync_all_camps_checkbox()
        self._schedule_lesson_rebuild()

    def _on_camp_item_changed(self, item):
        """方框状态变化 → 重建课程列表。"""
        if self._camp_updating:
            return
        self._sync_all_camps_checkbox()
        self._schedule_lesson_rebuild()

    def _on_camp_clicked(self, item):
        """点营名文字 = 把这个营加进课程列表（只增不减）。

        ★ 必须按击中点区分：点在左侧方框上时，Qt 也会发出 itemClicked，
          但那次的勾选切换已经由 itemChanged 处理了 —— 这里若再勾一次，
          用户「取消勾选」会被立刻改回去。
        """
        pos = self.lst_camps.viewport().mapFromGlobal(QCursor.pos())
        rect = self.lst_camps.visualItemRect(item)
        if pos.x() <= rect.left() + 24:
            return                      # 点在方框里，交给 itemChanged
        if item.checkState() != Qt.Checked:
            self._camp_updating = True
            item.setCheckState(Qt.Checked)   # 需要触发 itemChanged → 重建
            self._camp_updating = False
            self._sync_all_camps_checkbox()
            self._schedule_lesson_rebuild()

    def _on_camp_selected(self, row):
        """高亮行变化：只更新「当前营」。

        没有任何营被勾选时，课程列表显示当前高亮营（旧行为）；
        一旦有勾选，课程列表就由勾选的营决定，点文字不该把它换掉。
        """
        if row < 0 or row >= len(self.camps):
            return
        self.current_camp = self.camps[row]
        if not self._checked_camps():
            self._schedule_lesson_rebuild()

    def _schedule_lesson_rebuild(self):
        """勾选事件防抖：一次点击可能同时触发 itemChanged + rowChanged。"""
        if self._rebuild_scheduled:
            return
        self._rebuild_scheduled = True
        QTimer.singleShot(0, self._rebuild_lessons_from_camps)

    def _rebuild_lessons_from_camps(self):
        self._rebuild_scheduled = False
        picked = self._checked_camps()
        if not picked and self.current_camp:
            picked = [self.current_camp]
        keys = [getattr(c, 'camp_id', '') or getattr(c, 'name', str(c))
                for c in picked]
        old = [getattr(c, 'camp_id', '') or getattr(c, 'name', str(c))
               for c in self._camp_target]
        if keys == old and self.tbl_lessons.rowCount():
            return                      # 营没变 → 不重复拉课表 / 扫描
        self._camp_target = list(picked)
        self._load_camps_lessons(list(picked))

    # ── 课表加载（单营同步 / 多营后台）────────────────────────
    def load_lessons(self):
        """兼容入口：同步加载当前高亮营（旧调用与回归测试依赖）。"""
        if not self.current_camp or not self.platform:
            return
        self._camp_target = [self.current_camp]
        self._load_camps_lessons([self.current_camp], sync=True)

    def _load_camps_lessons(self, camps, sync=False):
        """把若干营的课表合并成一张课程表。

        ★ 单营走同步（最多一次请求，且 platform 有内存缓存）；
          多营走后台线程，边加载边追加行，UI 不会被 9 次网关请求冻住。
        """
        self._snapshot_lesson_checks()
        self._catalog_gen += 1
        gen = self._catalog_gen
        self._lesson_groups = []
        self.lessons = []
        self.row_of_lesson = {}
        self.lesson_of_row = {}
        self.camp_of_row = {}
        self._scan_counts = (0, 0)
        self.tbl_lessons.setRowCount(0)
        self.lbl_exist.setText('')
        self._update_lesson_title(camps, 0)
        self._update_lesson_header(0)
        if not camps or not self.platform:
            self.lbl_lesson_hint.setText('选择左侧营查看课程')
            return

        if sync or len(camps) == 1:
            for camp in camps:
                try:
                    cat = list(self.platform.camp_catalog(camp) or [])
                except Exception as e:
                    self._on_catalog_failed(gen, camp, str(e))
                    continue
                self._on_catalog_loaded(gen, camp, cat)
            self._on_catalog_finished(gen)
            return

        worker = CatalogWorker(self.platform, camps, gen)
        worker.loaded.connect(self._on_catalog_loaded)
        worker.failed.connect(self._on_catalog_failed)
        worker.finished_all.connect(self._on_catalog_finished)
        worker.finished.connect(self._prune_catalog_workers)
        # ★ 运行中的 QThread 必须保活，被 GC 析构会让 Qt 直接 abort
        self._catalog_workers.append(worker)
        self.lbl_lesson_hint.setText('正在加载 %d 个营的课表…' % len(camps))
        worker.start()

    def _prune_catalog_workers(self):
        self._catalog_workers = [w for w in self._catalog_workers
                                 if w.isRunning()]

    def _on_catalog_loaded(self, gen, camp, lessons):
        if gen != self._catalog_gen:
            return                      # 用户已改勾选 → 丢弃旧结果
        self._lesson_groups.append((camp, lessons))
        self._append_lesson_rows(camp, lessons)
        self._update_lesson_title([c for c, _ in self._lesson_groups],
                                  self.tbl_lessons.rowCount())
        self._update_lesson_header(0)
        n = self.tbl_lessons.rowCount()
        if len(self._lesson_groups) == 1:
            self.lbl_lesson_hint.setText(
                '共 %d 节 · 目录：%s'
                % (n, os.path.join(self.out_dir, self._camp_folder(camp))))
        else:
            self.lbl_lesson_hint.setText(
                '共 %d 节 · %d 个营 · 各自存到下载目录下的同名文件夹'
                % (n, len(self._lesson_groups)))

    def _on_catalog_failed(self, gen, camp, reason):
        if gen != self._catalog_gen:
            return
        self.log('加载课表失败：%s —— %s'
                 % (getattr(camp, 'name', str(camp)), reason))

    def _on_catalog_finished(self, gen):
        if gen != self._catalog_gen:
            return
        if not self._lesson_groups:
            self.lbl_lesson_hint.setText('课表加载失败，请检查网络后点「刷新」')
            return
        self._scan_existing(self._lesson_groups)

    def _update_lesson_title(self, camps, total=0):
        """课程列表标题：多营名用中文间隔号分隔、向左循环滚动。"""
        names = [getattr(c, 'name', str(c)) for c in camps]
        if not names:
            self.lbl_lessons.set_marquee('（0 节）', False)
            return
        if len(names) == 1:
            self.lbl_lessons.set_marquee(
                '%s（%d 节）' % (names[0], total), False,
                '当前显示：%s' % names[0])
            return
        text = (CAMP_SEPARATOR.join(names)
                + CAMP_SEPARATOR + '共 %d 节' % total)
        tip = ('已勾选 %d 个营（标题会向左循环滚动）：\n%s'
               % (len(names), '\n'.join(names)))
        self.lbl_lessons.set_marquee(text, True, tip)

    # ── 课程行 ─────────────────────────────────────────────
    @staticmethod
    def _lesson_key(le, camp):
        """跨「重建表格」稳定标识一节课（用来恢复勾选）。"""
        cname = getattr(camp, 'name', str(camp)) if camp else ''
        return (cname, repr(getattr(le, 'key', '')),
                getattr(le, 'title', ''), getattr(le, 'index', 0))

    def _snapshot_lesson_checks(self):
        keys = set()
        for row in range(self.tbl_lessons.rowCount()):
            cb = self.tbl_lessons.item(row, COL_CHECK)
            le = self.lesson_of_row.get(row)
            if cb is not None and le is not None \
                    and cb.checkState() == Qt.Checked:
                keys.add(self._lesson_key(le, self.camp_of_row.get(row)))
        self._checked_lesson_keys = keys

    def _append_lesson_rows(self, camp, lessons):
        """把「一个营」的整份课表追加到课程表末尾。"""
        cname = getattr(camp, 'name', str(camp))
        self.tbl_lessons.blockSignals(True)
        for i, le in enumerate(lessons):
            row = self.tbl_lessons.rowCount()
            self.tbl_lessons.insertRow(row)
            # ★ 键里必须带营：两个营的第 1 节 key 相同，
            #   直接拿 le.key 当键会互相覆盖（多营合并才会暴露）。
            self.row_of_lesson[self._lesson_key(le, camp)] = row
            self.lesson_of_row[row] = le
            self.camp_of_row[row] = camp   # ★ 每行记住自己的营
            self.lessons.append(le)

            cb = QTableWidgetItem('')
            cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                        | Qt.ItemIsSelectable)
            key = self._lesson_key(le, camp)
            cb.setCheckState(Qt.Checked if key in self._checked_lesson_keys
                             else Qt.Unchecked)
            self.tbl_lessons.setItem(row, COL_CHECK, cb)

            # ★ 标题前缀 = 该课在**原营**课表里的序号（1 起）。
            #   多营合并时**不重新编号**，所以不同营会看到重复的 01/02…
            #   这与成品文件名 `<序号>.<课名>.<日期>.mp4` 完全对应。
            seq = i + 1
            pref = QTableWidgetItem('%02d' % seq)
            pref.setTextAlignment(Qt.AlignCenter)
            pref.setToolTip('「%s」里的第 %d 节\n成品文件名前缀：%d.'
                            % (cname, seq, seq))
            self.tbl_lessons.setItem(row, COL_PREFIX, pref)

            title_item = QTableWidgetItem(le.title)
            title_item.setToolTip(
                '%s\n营：%s\n时间：%s\n类型：%s\n时长：%s'
                % (le.title, cname, le.when or '-', le.type or '-',
                   _fmt_dur(le.duration)))
            # ★ 状态词存在 STATE_ROLE 上，由 LessonTitleDelegate
            #   画在课名后面（单独配色）。
            title_item.setData(STATE_ROLE, '')
            self.tbl_lessons.setItem(row, COL_TITLE, title_item)

            # ★ 标题后缀 = 成品文件名里标题后面那段日期
            when_date = getattr(le, 'when_date', '') or ''
            suf = QTableWidgetItem(when_date)
            try:
                stem = xqd_platform.lesson_stem(le)
            except Exception:
                stem = '%d.%s' % (seq, le.title)
            suf.setToolTip('成品文件名里标题后面那段日期：\n'
                           '%s\n\n'
                           '★ 状态词不在这列 —— 它跟在课程名的后面。'
                           % (stem or '（无）'))
            self.tbl_lessons.setItem(row, COL_SUFFIX, suf)

            self.tbl_lessons.setItem(
                row, COL_DUR, QTableWidgetItem(_fmt_dur(le.duration)))

            # ★ 进度列不留空：重新加载时按历史 / 分片缓存 / 活动任务
            #   恢复这一节**实际的下载进度**（已存在 → 100%）。
            pct, tip = self._initial_progress(le, camp)
            bar = CellProgressBar()
            bar.setValue(pct)
            if tip:
                bar.setToolTip(tip)
            self.tbl_lessons.setCellWidget(row, COL_PROGRESS, bar)
        self.tbl_lessons.blockSignals(False)
        self.hdr_lessons.set_state(self._calc_check_state(self.tbl_lessons))

    # ── 进度列的「实际进度」恢复 ───────────────────────────────
    @staticmethod
    def _job_percent(job):
        """按任务当前量纲算百分比（分片视频用时长，直链音频用字节）。"""
        if job.get('finished'):
            return 100
        unit = job.get('unit') or 'dur'
        if unit == 'dur' and float(job.get('total_dur') or 0) > 0:
            return max(0, min(100, int(float(job.get('done_dur') or 0)
                                       * 100 / float(job['total_dur']))))
        if int(job.get('total') or 0) > 0:
            return max(0, min(100, int(int(job.get('down') or 0)
                                       * 100 / int(job['total']))))
        return 0

    def _initial_progress(self, le, camp):
        """课程列表（重新）加载时，这一节课**实际的下载进度**。

        优先级：正在下载的任务 > 下载历史 / 分片缓存 > 磁盘成品 > 0。
        ★ 用户 2026-11-07 指出：再次加载课表时「进度」一列全是空条，
          连已经下载完的课都看不出来 —— 必须把真实进度带回来。
        """
        # ① 还在跑 / 排队（切营再回来时进度条不能归零）
        for job in self.jobs.values():
            if job.get('lesson') is le:
                pct = self._job_percent(job)
                if pct:
                    return pct, '下载进度：%d%%' % pct
        try:
            out_path = self._out_path_for(camp, le)
        except Exception:
            return 0, ''            # 测试用的假 Lesson 没有 index 字段

        # ② 历史记录（跨会话记忆）+ 分片缓存（续传的本钱）
        rec = self.history.get(out_path)
        if rec is None:
            try:
                norm = os.path.normcase(os.path.abspath(out_path))
                for path, r in self.history.items():
                    if os.path.normcase(os.path.abspath(path)) == norm:
                        rec = r
                        break
            except Exception:
                rec = None
        if rec:
            if rec.get('state') == '已完成':
                return 100, '已完成（100%）'
            pct = 0
            td = float(rec.get('total_dur') or 0)
            dd = float(rec.get('done_dur') or 0)
            if td > 0 and dd > 0:
                pct = int(dd * 100 / td)
            total = int(rec.get('total') or 0)
            down = int(rec.get('down') or 0)
            if total > 0 and down > 0 and not pct:
                pct = int(down * 100 / total)
            cached, nseg, _ = xqd_history.parts_progress(
                xqd_history.parts_dir_for(out_path))
            if cached and total > 0:
                pct = max(pct, int(cached * 100 / total))
            pct = max(pct, int(getattr(le, 'progress', 0) or 0))
            pct = max(0, min(99, pct))   # 未完成不许显示满格
            if pct:
                return pct, ('未完成（可续传）：%d%%%s'
                             % (pct, ('，缓存分片 %d 个' % nseg)
                                if nseg else ''))
        # ③ 目录里已有成品但历史没记上（手工拷入 / 旧版本下的）
        try:
            if os.path.isfile(out_path) \
                    and os.path.getsize(out_path) > 10240:
                return 100, '已存在成品（100%）'
        except OSError:
            pass
        return 0, ''

    def _set_row_progress(self, row, pct, tip=''):
        """写课程列表「进度」列的进度条。"""
        bar = self.tbl_lessons.cellWidget(row, COL_PROGRESS)
        if bar is None:
            return
        bar.setValue(max(0, min(100, int(pct))))
        if tip:
            bar.setToolTip(tip)

    # ── 已下载检测 ───────────────────────────────────────────
    def rescan_existing(self):
        """手动重新扫描下载目录（多营时按当前表格里的营分组重扫）。"""
        groups = self._lesson_groups or (
            [(self.current_camp, self.lessons)] if self.current_camp else [])
        if not groups:
            QMessageBox.information(self, '提示', '请先选择一个营。')
            return
        self.checker.invalidate()
        self._scan_existing(groups)

    def _scan_existing(self, groups, lessons=None):
        """扫描下载目录，标出哪些课已经下过了（后台线程）。

        ★ v1.5.0：``groups = [(camp, lessons), ...]`` —— 多营合并后
          每个营有自己的输出目录，必须按营分别扫，不能共用一个 folder。
          仍兼容旧的两参数调用 ``_scan_existing(camp, lessons)``。

        比较维度：**文件名主键 + 时长**（见 xqd_dedupe 模块头的说明）。
        不查哈希（要全量读盘）、不联网查大小（违背「少请求」约束）。
        """
        if lessons is not None:
            groups = [(groups, lessons)]
        groups = list(groups or [])
        out_root = self.ed_out.text().strip() or default_out_dir()
        self.checker.out_root = out_root
        scan_groups = []
        for camp, cat in groups:
            folder = os.path.join(out_root, self._camp_folder(camp))
            self.checker.invalidate(folder)
            # 兼容旧目录名（`_Camp xxx (N节)_`），避免重复下载已有成品
            alt = xqd_dedupe.legacy_camp_folders(
                out_root, getattr(camp, 'name', str(camp)),
                getattr(camp, 'count', None))
            scan_groups.append((folder, cat, alt))
        if not scan_groups:
            return

        # ★ 旧扫描线程可能还在跑（ffprobe 在 SMB 网络盘上很慢）。
        #   **不能**直接 `self.scan_worker = 新对象` —— 旧对象引用一丢，
        #   Python GC 就会把它析构，而它还在运行 → Qt 检测到
        #   「QThread 在运行中被销毁」→ qFatal abort，进程直接消失。
        #   这里不 wait（会冻 UI），旧结果靠 _on_scan_done 的 sender 守卫丢弃。
        self._prune_scan_workers()

        worker = ScanWorker(self.checker, groups=scan_groups)
        worker.done.connect(self._on_scan_done)
        worker.finished_all.connect(self._on_scan_finished)
        self._scan_workers.append(worker)
        self.scan_worker = worker
        worker.start()

    def _prune_scan_workers(self):
        """摘掉已结束的扫描线程（已结束的可以安全 GC）。"""
        self._scan_workers = [w for w in self._scan_workers
                              if w.isRunning()]

    def _on_scan_done(self, result):
        """收到扫描结果，实时更新行状态。

        ★ 按 **lesson 引用** 定位行，不按行号 —— 切营后表格重建，
        行号含义已变，按行号回传会把新营的行标成旧营的判定。
        ★ v1.5.0：多营切换时旧扫描线程可能还在跑，结果必须丢弃
          （sender 不是当前 worker），否则计数与状态会串台。
        """
        who = self.sender()
        if who is not None and who is not self.scan_worker:
            return
        exist = 0
        broken = 0
        for le, ok, st in result:
            row = self._row_of_lesson_obj(le)
            if row is None:
                continue          # 这节课已不属于当前表（切营了），丢弃
            if ok:
                exist += 1
            else:
                broken += 1
            self._mark_existing(row, ok, st)
        self.lbl_exist.setText('正在检测已下载课程…')
        self._scan_counts = (exist, broken)
        # ★ 边扫边更新表头计数 —— 不用等整个扫描结束
        self._update_lesson_header(exist)

    def _row_of_lesson_obj(self, le):
        """按 lesson **对象引用**找当前行号；不在当前表里返回 None。"""
        if le is None:
            return None
        for row, cur in self.lesson_of_row.items():
            if cur is le:
                return row
        return None

    def _on_scan_finished(self):
        who = self.sender()
        if who is not None and who is not self.scan_worker:
            return
        exist, broken = getattr(self, '_scan_counts', (0, 0))
        # ★ 表头「课程」后面用括号显示「已下载课程数/全部课程数」
        self._update_lesson_header(exist)
        if exist or broken:
            self.lbl_exist.setText(
                '本目录已有 %d 节成品，已自动取消勾选并跳过%s'
                % (exist, ('；另有 %d 节文件不完整，将重新下载' % broken)
                   if broken else ''))
        else:
            self.lbl_exist.setText('')
        self.log('已下载检测：%d 节已存在，%d 节需重下' % (exist, broken))
        self.hdr_lessons.set_state(self._calc_check_state(self.tbl_lessons))

    def _update_lesson_header(self, exist=0):
        """更新「课程」列表头：课程 (已下载数/全部数)。

        ★ 用户要求：课程表头后面用括号标明「已下载课程数/全部课程数」，
          让人一眼看出这个营还剩多少没下。
        """
        total = self.tbl_lessons.rowCount()
        if not total:
            return
        self.tbl_lessons.horizontalHeaderItem(COL_TITLE).setText(
            '课程 (%d/%d)' % (exist, total))
        self.tbl_lessons.horizontalHeaderItem(COL_TITLE).setToolTip(
            '已下载课程数 / 全部课程数')

    def _mark_existing(self, row, ok, st):
        """把已存在的课标成「已存在」并取消勾选。

        ★ 不覆写「正在下载 / 已完成 / 失败」的行 —— 扫描是异步的，
        结果回来时那一节可能已经在下载或下完了，这时它的状态比
        扫描结论更权威。
        """
        le = self.lesson_of_row.get(row)
        if not le:
            return
        # ★ 不覆写「排队中 / 正在下载」的行 ——
        #   扫描是异步的，结果回来时那一节可能已经在队列里或正在下载，
        #   这时它的状态比扫描结论更权威。
        #   （「排队中」也要挡：否则迟到的扫描结果会把刚入队的课
        #    取消勾选，用户看到的就是「启动了下载但勾选却是空的」。）
        #
        # ★ 但「已完成 / 失败」**不能**挡：
        #   camp_catalog 缓存了 Lesson 对象，重新加载课表时状态会残留。
        #   上一轮下完的课本轮扫描发现文件确实存在 —— 这时就应该标成
        #   「已存在」并取消勾选，否则用户会看到下过的课又被当成待下载。
        if le.state in ('queued', 'running'):
            return
        le.state = 'exists' if ok else 'needs_redl'
        le.out_path = st.get('path') or ''

        item = self.tbl_lessons.item(row, COL_TITLE)
        if not item:
            return
        # ★ v1.5.0：序号已独立成「标题前缀」列，课名列只放纯课名
        item.setText(le.title)
        # ★ 状态词跟在**课名后面**（STATE_ROLE，委托自绘并单独着色）
        if ok:
            item.setData(STATE_ROLE, '已存在')
            mb = st.get('size', 0) / 1048576.0
            item.setToolTip('%s\n已存在：%s\n大小：%.1f MB%s'
                            % (le.title, st.get('path'), mb,
                               ('\n时长：%s' % _fmt_dur(st['duration']))
                               if st.get('duration') else ''))
            # ★「进度」列显示实际进度：已存在的成品 = 100%，不留空条
            self._set_row_progress(row, 100, '已存在成品（100%）')
        else:
            item.setData(STATE_ROLE, '需重下')
            item.setToolTip('%s\n%s' % (le.title, st.get('reason') or ''))
            # 残缺文件：保留历史 / 分片缓存里的真实部分进度
            bar = self.tbl_lessons.cellWidget(row, COL_PROGRESS)
            cur = bar.value() if bar is not None else 0
            if cur >= 100:
                cur = 0      # 之前乐观按「文件存在」置满，扫描证明是残缺
            self._set_row_progress(row, cur, '文件不完整，需要重下')

        cb = self.tbl_lessons.item(row, COL_CHECK)
        if cb:
            # 已存在 → 取消勾选（不用再下）；残缺 → 勾上（需要重下）
            cb.setCheckState(Qt.Unchecked if ok else Qt.Checked)

    # ── 选择 ───────────────────────────────────────────────
    def _on_header_toggled(self, want_all):
        """课程表表头勾选框：全选 / 全不选。"""
        self._set_all_checks(self.tbl_lessons, want_all)
        self.hdr_lessons.set_state('all' if want_all else 'none')

    def _on_task_header_toggled(self, want_all):
        """任务表表头勾选框：全选 / 全不选。"""
        self._set_all_checks(self.tbl_tasks, want_all)
        self.hdr_tasks.set_state('all' if want_all else 'none')

    def _set_all_checks(self, table, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        table.blockSignals(True)
        for i in range(table.rowCount()):
            item = table.item(i, 0)
            if item:
                item.setCheckState(state)
        table.blockSignals(False)

    def _on_lesson_item_changed(self, item):
        """任一行勾选变化 → 同步表头三态。"""
        if item.column() != 0:
            return
        self.hdr_lessons.set_state(self._calc_check_state(self.tbl_lessons))

    def _on_task_item_changed(self, item):
        if item.column() != 0:
            return
        self.hdr_tasks.set_state(self._calc_check_state(self.tbl_tasks))

    @staticmethod
    def _calc_check_state(table):
        total = table.rowCount()
        if total == 0:
            return 'none'
        checked = 0
        for i in range(total):
            it = table.item(i, 0)
            if it and it.checkState() == Qt.Checked:
                checked += 1
        if checked == 0:
            return 'none'
        if checked == total:
            return 'all'
        return 'partial'

    def _select_all(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.tbl_lessons.rowCount()):
            item = self.tbl_lessons.item(i, COL_CHECK)
            if item:
                item.setCheckState(state)
        self.hdr_lessons.set_state(
            'all' if checked else 'none')

    def _checked_lessons(self):
        out = []
        for i in range(self.tbl_lessons.rowCount()):
            item = self.tbl_lessons.item(i, COL_CHECK)
            if item and item.checkState() == Qt.Checked:
                le = self.lesson_of_row.get(i)
                if le:
                    out.append((i, le))
        return out

    # ── 下载 ───────────────────────────────────────────────
    def _camp_folder(self, camp):
        """营的输出目录名。

        ⚠️ 下载与检测必须用**同一个**目录名，否则扫描永远找不到文件。
        这里统一取 camp.name（Camp 对象传进 safe_name 会被 str() 成
        "<Camp 五行养生音乐 (10节)>"，与目录名对不上）。
        """
        name = camp.name if hasattr(camp, 'name') else str(camp)
        return xqd_platform.safe_name(name)

    def _out_path_for(self, camp, lesson, used=None):
        """成品路径 —— **固定用规范名**，绝不加 ``-1`` 后缀。

        为什么不加后缀：``序号.课名.日期`` 在营内已唯一（序号参与主键），
        加后缀只会制造「同一节课两个文件」的混乱。正确做法是：
          * 已有完整成品 → 跳过（不下载）
          * 已有残缺文件 → 删掉它，用规范名重新下载（覆盖）
        """
        name = (xqd_platform.lesson_stem(lesson)
                + xqd_platform.expected_ext(lesson))
        folder = os.path.join(self.out_dir, self._camp_folder(camp))
        return os.path.join(folder, name)
    def start_download_selected(self):
        picked = self._checked_lessons()
        if not picked:
            QMessageBox.information(self, '提示', '请先勾选要下载的课程。')
            return
        self._start_downloads(picked)

    def _on_row_double_click(self, row, col):
        """双击某行 = 下载该节课。"""
        self.start_download_single(row)

    def _on_download_one_clicked(self):
        """「下载此课」：用当前选中行。"""
        row = self.tbl_lessons.currentRow()
        if row < 0:
            QMessageBox.information(self, '提示', '请先选中一节课。')
            return
        self.start_download_single(row)

    def start_download_single(self, row):
        le = self.lesson_of_row.get(row)
        if le:
            self._start_downloads([(row, le)])

    def _start_downloads(self, picked):
        if not self.platform or not self.cookie:
            QMessageBox.warning(self, '未授权', '请先完成授权。')
            return
        out_root = self.ed_out.text().strip() or default_out_dir()
        if not os.path.isdir(out_root):
            try:
                os.makedirs(out_root, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, '目录错误',
                                     '无法创建目录：%s\n%s' % (out_root, e))
                return

        quality = self.cmb_quality.currentData() or 'max'

        # 若后台扫描还在跑，先等它结束（否则会漏判「已存在」）
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.wait(5000)

        # ★ v1.5.0：多营合并后每行属于不同的营 —— 输出目录、已下载检测、
        #   历史记录、下载任务都必须用**这一行自己的营**，不能用 current_camp。
        #   按营缓存 folder / alt，避免同一营的课反复扫根目录。
        folder_of = {}
        alt_of = {}

        def _for_camp(c):
            key = getattr(c, 'name', str(c))
            if key not in folder_of:
                folder_of[key] = os.path.join(out_root, self._camp_folder(c))
                alt_of[key] = xqd_dedupe.legacy_camp_folders(
                    out_root, key, getattr(c, 'count', None))
            return folder_of[key], alt_of[key]

        started = 0
        skipped = 0
        redownload = 0
        for entry in picked:
            row, le = entry[0], entry[1]
            # 兼容旧调用 ``(row, lesson)``；新调用可带第三个元素 camp
            camp = entry[2] if len(entry) > 2 else (
                self.camp_of_row.get(row) or self.current_camp)
            folder, alt = _for_camp(camp)
            # ★ 已下载检测：整组判定（主名 + -N 重名后缀）
            #   ok      → 已有完整成品，跳过（只记日志，不弹窗）
            #   broken  → 有残缺文件，删掉后用规范名重新下载
            #   missing → 正常下载
            stem = xqd_platform.lesson_stem(le)
            st = self.checker.check_group(folder, stem, le.duration,
                                          alt_folders=alt)
            if st['status'] == 'ok':
                skipped += 1
                le.state = 'exists'
                le.out_path = st['path']
                self._mark_existing(row, True, st)
                self.log('跳过（已存在且完整）：%s' % le.title)
                continue

            out_path = self._out_path_for(camp, le)

            if st['status'] == 'broken':
                # 残缺文件：删掉再用规范名重下（避免出现 xxx-1 这种重复名）
                removed = self.checker.purge_broken(
                    folder, stem, le.duration, alt_folders=alt)
                redownload += 1
                self.log('重下（%s）：%s —— 已清理残缺文件 %d 个'
                         % (st['reason'], le.title, len(removed)))

            le.state = 'queued'
            le.out_path = out_path

            # 已经在跑或已在队列里的课不再重复入队
            if id(le) in self._queued_lessons():
                self.log('已在下载队列中，跳过重复入队：%s' % le.title)
                continue

            # 画质在入队时锁定，避免中途改下拉框影响已排队的课
            self._job_seq += 1
            job_id = self._job_seq
            seg_dir = xqd_history.parts_dir_for(out_path)
            # ★ 上次没下完的分片还在 → 本次可以接着下（跨进程续传）
            cached_bytes, cached_segs, _ = xqd_history.parts_progress(seg_dir)
            self.jobs[job_id] = {'row': row, 'lesson': le, 'camp': camp,
                                 'out_path': out_path,
                                 # ★ 进度跟踪（用于估算剩余时间）
                                 'down': 0, 'total': 0, 'speed': 0.0,
                                 'done_dur': 0.0, 'total_dur': 0.0,
                                 'unit': 'dur', 'eta': None,
                                 'phase': '', 'meter': SpeedMeter(),
                                 # ★ 字节速率计（给「速度」列显示）
                                 'bmeter': SpeedMeter(),
                                 # ★ 内容速率（内容秒/秒）—— 算 ETA 用
                                 'rate_dur': 0.0,
                                 # ★ 分片缓存（跨进程续传）
                                 'seg_dir': seg_dir,
                                 'cached_bytes': cached_bytes,
                                 'cached_segs': cached_segs,
                                 'eta_fixed': 0.0, 't0': time.time()}
            self.pending_queue.append((job_id, le, camp, out_path,
                                       quality))
            self._set_row_state(row, '排队中', None)
            # ★ 入队即勾选 —— 复选框要反映「这节课在下载流程里」。
            #   之前只靠用户手勾，「下载此课」/ 双击触发的下载就一直是
            #   空框，看上去像没在下载。
            cb = self.tbl_lessons.item(row, COL_CHECK)
            if cb:
                cb.setCheckState(Qt.Checked)
            started += 1

        # 全部已下载**不弹窗**，只在日志里说明（用户明确要求）
        msg = '已启动 %d 个下载任务' % started
        if skipped:
            msg += '，跳过 %d 个（已存在且完整）' % skipped
        if redownload:
            msg += '，重下 %d 个（原文件残缺）' % redownload
        self.log(msg + '。')

        # 真正开跑（受网络并发上限限制；封装阶段会提前归还槽位）
        self._pump_queue()

    # ── 下载队列（限流 / 封装流水线）────────────────────────
    def _net_active(self):
        """当前真正占着带宽的任务数（不含已进入封装/校验的）。"""
        return sum(1 for jid in self.running_workers
                   if jid not in self.network_released)

    def _release_idle_slots(self):
        """把已进入「封装/校验」的任务从网络槽位里摘出来。

        返回本次**新释放**的 job_id 集合（调用方据此在日志里标注）。
        受 MAX_MUX_WORKERS 限制：本地封装太多会抢网络盘的写 IO，
        没抢到槽位的任务暂时继续占着网络槽位，等下一个封装结束再释放。
        """
        # 清掉已结束任务的残留（正常在 _on_download_completed 里清，
        # 这里兜底，防止某条异常路径留下幽灵槽位把并发数卡死）。
        self.network_released.intersection_update(self.running_workers)
        freed = set()
        for jid in list(self.running_workers):
            if len(self.network_released) >= MAX_MUX_WORKERS:
                break
            if jid in self.network_released:
                continue
            job = self.jobs.get(jid)
            if not job or job.get('phase') not in LOCAL_PHASES:
                continue
            self.network_released.add(jid)
            freed.add(jid)
        return freed

    def _pump_queue(self):
        """从队列里取任务开跑，直到**网络**并发达到上限。

        ★ v1.5.0 流水线：占槽位的是「还没下完分片」的任务，不是
          「线程还活着」的任务。进入封装/校验的线程已经不联网了，
          它的槽位由 _on_phase 里的 _release_idle_slots 提前归还。
          所以「3 个在下载 + 最多 2 个在封装」是允许且期望的状态。

        放行时机有三处：启动下载、阶段切到封装、任务完成回调。
        """
        while (self.pending_queue
               and self._net_active() < MAX_LESSON_WORKERS
               # 硬上限：网络槽 + 封装槽，防止异常情况下无限起线程
               and len(self.running_workers)
               < MAX_LESSON_WORKERS + MAX_MUX_WORKERS):
            # ★ 暂停期间不启动新的下载任务 —— 否则「暂停」只是暂停了
            #   已在跑的那几节，队列里的会继续开新连接。
            if self.control is not None and self.control.is_paused():
                break
            job_id, le, camp, out_path, quality = self.pending_queue.pop(0)
            if job_id in self.running_workers:
                continue
            # ★ 分片缓存目录：同一节课恒定 → 跨进程续传
            seg_dir = xqd_history.parts_dir_for(out_path)
            th = DownloadWorker(self.platform, camp, le, out_path,
                                quality, job_id, control=self.control,
                                seg_dir=seg_dir)
            th.progress.connect(self._on_progress)
            th.phase.connect(self._on_phase)
            th.completed.connect(self._on_download_completed)
            th.log.connect(self.log)
            self.active_threads.append(th)
            self.running_workers.add(job_id)
            le.state = 'running'
            le.out_path = out_path
            # 任务真正开始跑的时刻（用于估算总用时）
            job = self.jobs.get(job_id)
            if job is not None:
                job['t0'] = time.time()
                job['phase'] = '解析'
            # 按 lesson 引用定位当前行（切营后行号已失效）
            row = self._row_of_lesson_obj(le)
            if row is not None:
                self._set_row_state(row, '下载中', None)
            self._add_task(le, camp, out_path, '下载中', job_id)
            th.start()
        # 有任务在跑 → 暂停按钮可用
        self._sync_pause_button()

    def _queued_lessons(self):
        """已在队列中（或正在跑）的 lesson 对象 id 集合。"""
        out = set()
        for jid, le, _, _, _ in self.pending_queue:
            out.add(id(le))
        for jid in self.running_workers:
            job = self.jobs.get(jid)
            if job:
                out.add(id(job['lesson']))
        return out

    def _on_progress(self, job_id, down, total, done_dur, total_dur):
        """下载进度回调。

        ★ 传进来的 down/total 是**字节数**（不是百分比），
          这样才能算速率、进而算出「还剩多久」。

        ★ 两个量纲要分开记（这是实测踩过的坑）：
          - **字节速率**（B/s）→ 显示在「速度」列，必须和系统
            任务管理器的网络/磁盘速率能对上，用户才认得出。
          - **内容速率**（内容秒/秒，即倍速）→ 用于算 ETA。
            用内容时长算 ETA 更准：清单里每片时长是精确已知的，
            而总字节数是抽样外推的（虽有 -0.7% 误差但仍是估算）。
          早期版本把内容速率直接当字节速率显示，于是界面上出现
          「248B/s」这种荒唐数字（其实是 248 倍速）。
        """
        job = self.jobs.get(job_id)
        if not job:
            return
        job['down'] = down
        job['total'] = total
        job['done_dur'] = done_dur
        job['total_dur'] = total_dur

        # ── 字节速率（给「速度」列显示）──
        bmeter = job.get('bmeter')
        if bmeter is None:
            bmeter = job['bmeter'] = SpeedMeter()
        bmeter.add(down)
        job['speed'] = bmeter.speed()

        # ── 内容速率（给 ETA 用）──
        if total_dur and total_dur > 0:
            meter = job.get('meter')
            if meter is None:
                meter = job['meter'] = SpeedMeter()
            meter.add(done_dur)
            job['rate_dur'] = meter.speed()
            job['unit'] = 'dur'
            pct = int(done_dur * 100 / total_dur)
        else:
            # 直链音频：没有分片时长，退回字节口径
            job['rate_dur'] = job['speed']
            job['unit'] = 'byte'
            pct = int(down * 100 / total) if total > 0 else 0

        job['eta'] = self._compute_eta(job)
        self._refresh_task_row(job_id)

        # ★ 记录下载进度（供第二次打开工具时恢复）
        #   节流：每 3 秒最多落盘一次，避免频繁写盘。
        now = time.time()
        if now - self._hist_last_flush > 3.0:
            self._hist_last_flush = now
            le = job.get('lesson')
            self._record_history(
                job.get('out_path') or '',
                (le.title if le else ''),
                camp=getattr(job.get('camp'), 'name', '') or '',
                state='下载中', down=down, total=total,
                done_dur=done_dur, total_dur=total_dur,
                duration=(le.duration if le else 0) or 0)
            self._flush_history()

        # ★ 同时把百分比记在 Lesson 上 —— 重新加载课程表时
        #   _initial_progress 能立刻带回来（历史落盘有 3 秒节流）。
        le = job.get('lesson')
        if le is not None:
            le.progress = pct
        # 只有当这一行还属于当前显示的营时才更新进度条
        row = self._row_of_lesson_obj(job['lesson'])
        if row is None:
            return
        self._set_row_progress(row, pct, '下载进度：%d%%' % pct)

    def _compute_eta(self, job):
        """按当前速率算剩余秒数。

        ★ 用「剩余量 / 速率」而不是「已用时间 × 总时长 / 已用时间」：
          后者是**平均速度**推算，网络一慢下来就完全不跟手。
          这里用的是最近几秒的**实时速率**，速度一变估算立刻跟着变。
        """
        unit = job.get('unit') or 'dur'
        if unit == 'dur':
            total = job.get('total_dur') or 0
            done = job.get('done_dur') or 0
            speed = job.get('rate_dur') or 0.0
        else:
            total = job.get('total') or 0
            done = job.get('down') or 0
            speed = job.get('speed') or 0.0
        if total <= 0:
            return None
        if speed <= 0:
            return None
        remain = max(0.0, total - done)
        return remain / speed

    def _on_phase(self, job_id, phase):
        """下载阶段变化（解析 / 下载 / 封装 / 校验）。

        ★ 三处状态一一对应（用户 2026-11-07 指出）：
          阶段一变，**课程列表后缀**、**下载管理状态列**、**运行日志**
          三处同时更新，而且用的是**同一个词**。
          以前只有下载管理表会变，课程列表一直停在「下载中…」——
          同一节课两处说法对不上。
        """
        job = self.jobs.get(job_id)
        if not job:
            return
        old = job.get('phase') or ''
        job['phase'] = phase
        if phase == '封装':
            job['eta_fixed'] = self._estimate_mux_seconds(job)
        elif phase == '校验':
            # 只剩 ffprobe 校验了，几秒的事
            job['eta_fixed'] = 3.0

        # ★ 流水线：一进入封装/校验就把网络槽位还回去，立刻放行下一节。
        #   放在暂停判断之前 —— 暂停只禁止「开新任务」，槽位记账仍要正确；
        #   _pump_queue 内部会自己检查暂停状态。
        freed = (self._release_idle_slots()
                 if phase in LOCAL_PHASES else set())
        if freed:
            self._pump_queue()

        self._refresh_task_row(job_id)

        word = PHASE_TEXT.get(phase, phase)
        # 暂停中不改状态（暂停是用户主动的操作，优先级更高）
        if self._paused:
            return
        # ★ 两处状态列同步
        self._set_both_states(job_id, word)
        # ★ 运行日志也记一笔 —— 否则日志里只有「开始下载」，
        #   用户查不到这一节当前到底在干嘛。
        if word != PHASE_TEXT.get(old, old):
            le = job.get('lesson')
            title = le.title if le else ''
            note = ('（网络已释放，可并行下一节）'
                    if job_id in freed else '')
            self.log_state('%s：%s%s' % (word, title, note))

    def _estimate_mux_seconds(self, job):
        """估算「转封装 + 校验」还要多久。

        转封装 = cat 字节拼接（受 Z 盘写入速度限制）+ ffmpeg 重封装
        （受 CPU/IO 限制）。用片���总大小 / Z 盘速度 + 时长/常数 粗估。
        """
        total = job.get('total') or 0
        dur = 0.0
        le = job.get('lesson')
        if le is not None:
            dur = float(le.duration or 0)
        secs = (total / MUX_DISK_SPEED) if total else 0.0
        secs += dur / 60.0            # ffmpeg 大约 60x 实时
        secs += 3.0                  # ffprobe 校验
        return max(3.0, secs)

    # ── 剩余时间估算 ────────────────────────────────────────
    def _job_eta(self, job):
        """返回 (剩余秒数, 说明文字)。

        估算依据：
          * 下载阶段：剩余量 / 实时速率（速率随网络波动，估算跟着变）
          * 封装阶段：用一次性估算值（eta_fixed）
        """
        phase = job.get('phase') or '下载'
        if phase in ('封装', '校验'):
            eta = job.get('eta_fixed')
            if eta:
                return eta, ''
            return None, ''
        eta = job.get('eta')
        if eta is None:
            # 速率还没测出来 —— 用「最近一次有效速率」兜底
            unit = job.get('unit') or 'dur'
            if unit == 'dur':
                meter = job.get('meter')
                rate = meter.last_speed if meter is not None else 0
                total = job.get('total_dur') or 0
                done = job.get('done_dur') or 0
            else:
                meter = job.get('bmeter')
                rate = meter.last_speed if meter is not None else 0
                total = job.get('total') or 0
                done = job.get('down') or 0
            if not rate or total <= 0:
                return None, ''
            return max(0.0, total - done) / rate, ''
        return eta, ''

    def _refresh_task_row(self, job_id):
        """刷新下载管理表里某个任务的「大小 / 速度 / 剩余时间」三列。"""
        r = self._task_row_of_job.get(job_id)
        if r is None or r >= self.tbl_tasks.rowCount():
            return
        job = self.jobs.get(job_id)
        if not job:
            return
        # ★ 已结束的任务不再刷新（最后一列是「用时 …」，不能被覆盖）
        if job.get('finished'):
            return
        total = job.get('total') or 0
        down = job.get('down') or 0
        phase = job.get('phase') or '下载'

        # 状态列：下载中显示阶段（解析/下载/封装/校验）
        #
        # ★ 守卫的坑（实测踩过）：原来写的是
        #     cur.text() in ('下载中', '排队中', phase_text)
        #   只允许从「下载中/排队中」切进来 —— 于是状态变成「解析中」后
        #   就再也变不回「下载中」，界面上一���卡在「解析中」，
        #   实际早就开始下载了。
        #   正确做法：允许在**所有进行中阶段**之间自由切换，
        #   只保护终态（已完成/失败）不被覆盖。
        phase_text = PHASE_TEXT.get(phase)
        if phase_text:
            cur = self.tbl_tasks.item(r, 2)
            if cur is not None and cur.text() in PHASE_TEXTS:
                cur.setText(phase_text)

        # 大小：下载/封装中显示「已下/总量」，完成后显示成品大小
        if total > 0 and phase in ('下载', '封装', '校验'):
            # ★ 紧凑写法：列宽有限，"42.1/145 MB" 比 "42.1/145.0 MB" 省地方
            self.tbl_tasks.setItem(
                r, 3, QTableWidgetItem('%.1f/%.0f MB'
                                       % (down / 1048576.0,
                                          total / 1048576.0)))
        else:
            le = job.get('lesson')
            path = (le.out_path if le else '') or ''
            if path and os.path.isfile(path):
                mb = os.path.getsize(path) / 1048576.0
                self.tbl_tasks.setItem(
                    r, 3, QTableWidgetItem('%.1f MB' % mb))

        # 速度
        self.tbl_tasks.setItem(
            r, 4, QTableWidgetItem(fmt_speed(job.get('speed') or 0)))

        # 剩余时间
        eta, note = self._job_eta(job)
        if eta is None:
            txt = '--'
        else:
            txt = fmt_dur(eta)
        if note:
            txt = '%s %s' % (txt, note)
        it = self.tbl_tasks.item(r, 5)
        if it is None:
            self.tbl_tasks.setItem(r, 5, QTableWidgetItem(txt))
        else:
            it.setText(txt)

    def _refresh_all_task_rows(self):
        """刷新**在跑**任务的行。

        ★ 只刷在跑的：已完成的行最后一列是「用时 …」，
          要是这里也刷，就会被覆盖回「--」。
        """
        for job_id in list(self.running_workers):
            self._refresh_task_row(job_id)

    def _update_global_eta(self):
        """更新「下载管理」标题旁的全局剩余时间。

        全局剩余 = 在跑任务剩余之和 + 排队任务按**实测速率**折算。
        ★ 排队任务用实测速率（而不是固定码率）折算，
          这样网络快就显示快、网络慢就显示慢。
        """
        total_eta = 0.0
        n_run = 0
        n_wait = len(self.pending_queue)
        for job_id in self.running_workers:
            job = self.jobs.get(job_id)
            if not job:
                continue
            n_run += 1
            eta, _ = self._job_eta(job)
            if eta:
                total_eta += eta
        # 排队任务：按「每秒能下多少秒的内容」折算
        # ★ 这里要用**内容速率**（rate_dur，秒内容/秒），
        #   不是字节速率 —— 排队任务折算的是「内容还要多久下完」。
        rates = []
        for job_id in self.running_workers:
            # 封装中的任务不再产生下载速率，别把它算进平均带宽
            if job_id in self.network_released:
                continue
            job = self.jobs.get(job_id)
            if not job:
                continue
            if (job.get('unit') or 'dur') == 'dur' and job.get('rate_dur'):
                rates.append(job['rate_dur'])
        if rates and n_wait:
            rate = sum(rates) / len(rates)      # 秒内容 / 秒时间
            for _jid, le, _c, _p, _q in list(self.pending_queue):
                dur = float(le.duration or 0)
                total_eta += dur / rate
        if not n_run and not n_wait:
            self.lbl_task_eta.setText('')
            return
        # ★ 把「在跑」拆成下载 / 封装两部分：用户能直接看出流水线在跑，
        #   而不是误以为并发上限被突破或某节课卡住了。
        n_local = len(self.network_released & self.running_workers)
        self.lbl_task_eta.setText(
            '剩余约 %s · %d 个在跑（%d 下载 / %d 封装）/ %d 个排队'
            % (fmt_dur(total_eta), n_run, n_run - n_local, n_local,
               n_wait))

    def _on_download_completed(self, job_id, ok, msg, out_path):
        """下载完成（成功或失败都走这里）—— 唯一的完成入口。

        ★ 按 **lesson 引用** 定位当前行，不按入队时记下的行号。
        下载可能持续好几分钟，期间用户随时可能切营；行号一旦失效，
        完成状态就会写到别的课的行上。
        """
        # 先释放槽位，让队列里的下一节开跑。
        # ★ 完成的是封装任务时，会空出一个「本地封装槽位」——
        #   之前因 MAX_MUX_WORKERS 没抢到槽位、仍占着网络槽位的任务
        #   这时就能把带宽还回去，于是可能连续放行两节。
        self.running_workers.discard(job_id)
        self.network_released.discard(job_id)
        self._release_idle_slots()
        self._pump_queue()
        self._sync_pause_button()

        job = self.jobs.get(job_id)
        if not job:
            return
        le = job['lesson']
        if le is None:
            return
        row = self._row_of_lesson_obj(le)

        if ok:
            le.state = 'done'
            le.progress = 100
            le.out_path = out_path or le.out_path
            # ★ 两处状态同步（课程列表后缀 + 下载管理状态列）
            self._set_both_states(job_id, '已完成', msg, force=True)
            row = self._row_of_lesson_obj(le)
            if row is not None:
                self._set_row_progress(row, 100, '已完成（100%）')
            self._update_task(job_id, '已完成', msg)
            # 下载完让目录缓存失效，下次扫描能认到新文件
            if le.out_path:
                self.checker.invalidate(os.path.dirname(le.out_path))
            self.log('已完成：%s（%s）' % (le.title, msg))
        else:
            le.state = 'failed'
            # ★ 两处状态同步
            self._set_both_states(job_id, '失败', msg, force=True)
            row = self._row_of_lesson_obj(le)
            if row is not None:
                # 失败后自动重新勾选，方便「再勾选 → 重复批量下载」
                item = self.tbl_lessons.item(row, COL_CHECK)
                if item:
                    item.setCheckState(Qt.Checked)
            self._update_task(job_id, '失败', msg)
            self.log('失败：%s —— %s（已重新勾选，可再点「下载选中」重试）'
                     % (le.title, msg))

    # ── 下载历史（跨会话记忆）────────────────────────────────
    def _record_history(self, out_path, title, camp='', state='',
                        down=0, total=0, done_dur=0.0, total_dur=0.0,
                        size=0, duration=0):
        """把一条下载记录写进历史（内存），供落盘。

        ★ 按 **成品路径** 作主键：同一节课重下不会产生两条记录。
        """
        if not out_path:
            return
        rec = xqd_history.make_record(
            out_path, title, camp=camp, state=state, size=size,
            down=down, total=total, done_dur=done_dur, total_dur=total_dur,
            duration=duration)
        xqd_history.merge(self.history, rec)

    def _flush_history(self):
        """把历史落盘（延迟一点，避免频繁写盘）。"""
        items = xqd_history.sort_items(self.history)
        try:
            xqd_history.save_history(items)
        except Exception as e:
            self.log('保存下载历史失败：%s' % e)

    def _restore_history_tasks(self):
        """★ 第二次打开工具时，把上次的下载列表恢复进「下载管理」表。

        恢复的只是**历史记录**（哪些课下过、下到哪了），
        不会自动重新开始下载 —— 要续传的话，重新勾选那一课即可
        （已下分片还在缓存里，会直接跳过）。
        """
        if not self.history:
            return
        items = xqd_history.sort_items(self.history)
        for rec in items:
            path = rec.get('path') or ''
            if not path:
                continue
            state = rec.get('state') or ''
            title = rec.get('title') or os.path.basename(path)
            r = self.tbl_tasks.rowCount()
            self.tbl_tasks.insertRow(r)

            cb = QTableWidgetItem('')
            cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                        | Qt.ItemIsSelectable)
            cb.setCheckState(Qt.Unchecked)
            self.tbl_tasks.setItem(r, 0, cb)

            name_item = QTableWidgetItem(title)
            name_item.setData(Qt.UserRole, path)
            name_item.setToolTip(path)
            self.tbl_tasks.setItem(r, 1, name_item)

            # 状态：上次的结论 + 是否还有可续传的分片
            seg_dir = xqd_history.parts_dir_for(path)
            cached, _cnt, _tot = xqd_history.parts_progress(seg_dir)
            if state == '已完成':
                label = '已完成'
            elif state == '失败':
                label = '失败'
            elif cached > 0:
                label = '未完成（可续传）'
            else:
                label = '未完成'
            self.tbl_tasks.setItem(r, 2, QTableWidgetItem(label))

            # 大小：已下/总量；有缓存分片时显示已下的量
            down = rec.get('down') or 0
            total = rec.get('total') or 0
            if cached > 0:
                down = cached
            if total > 0:
                self.tbl_tasks.setItem(
                    r, 3, QTableWidgetItem('%.1f/%.0f MB'
                                           % (down / 1048576.0,
                                              total / 1048576.0)))
            else:
                sz = rec.get('size') or 0
                if sz:
                    self.tbl_tasks.setItem(
                        r, 3, QTableWidgetItem('%.1f MB' % (sz / 1048576.0)))
                else:
                    self.tbl_tasks.setItem(r, 3, QTableWidgetItem(''))
            self.tbl_tasks.setItem(r, 4, QTableWidgetItem('--'))
            self.tbl_tasks.setItem(r, 5, QTableWidgetItem('--'))

        self.log('已恢复上次下载列表：%d 条记录。' % len(items))

    # ── 暂停 / 继续 ────────────────────────────────────────
    def toggle_pause(self):
        """暂停 / 继续所有下载。

        暂停是**协作式**的：各下载线程在取下一个分片前检查标志并等待，
        已经下好的分片保留在临时目录里，继续后接着下，不会从头再来。
        """
        paused = self.control.toggle()
        self._paused = paused
        if paused:
            self.btn_pause.setText('继续')
            self.btn_pause.setObjectName('Primary')
            self.log('⏸ 已暂停所有下载（已下好的分片会保留，点「继续」接着下）。')
            self._set_all_running_state('已暂停')
        else:
            self.btn_pause.setText('暂停')
            self.btn_pause.setObjectName('PauseBtn')
            self.log('▶ 已继续下载。')
            # ★ 恢复后回到各任务**真实的阶段**，不能一律写「下载中…」——
            #   暂停时可能正处在封装/校验，笼统写「下载中」会对不上号。
            self._resume_states()
            # ★ 暂停期间若有任务结束（失败/中止），队列没被放行；
            #   继续时立刻补上，避免带宽空着却不开新任务。
            self._pump_queue()
        self._apply_style()

    def _resume_states(self):
        """继续下载后，把两处状态恢复成各任务当前的实际阶段。"""
        for job_id in list(self.running_workers):
            job = self.jobs.get(job_id)
            if not job:
                continue
            word = PHASE_TEXT.get(job.get('phase') or '', '下载中')
            row = self._row_of_lesson_obj(job['lesson'])
            if row is not None:
                self._set_row_state(row, word, None)
            r = self._task_row_of_job.get(job_id)
            if r is not None and r < self.tbl_tasks.rowCount():
                cur = self.tbl_tasks.item(r, 2)
                if cur is not None:
                    cur.setText(word)
        for job_id, le, _c, _p, _q in list(self.pending_queue):
            row = self._row_of_lesson_obj(le)
            if row is not None:
                self._set_row_state(row, '排队中', None)

    def _set_all_running_state(self, state):
        """把所有「正在下载 / 排队中」的行统一改成某个状态。

        state='已暂停' 时，排队中的课也要标成已暂停 —— 整个下载流程
        都停住了，显示「排队中」会让人以为还在跑。

        ★ 两处都改（用户 2026-11-07 指出状态要一一对应）：
          以前只改课程列表，下载管理表的状态列还停在「封装中」，
          暂停了看起来还在封装。
        """
        for job_id in list(self.running_workers):
            job = self.jobs.get(job_id)
            if not job:
                continue
            row = self._row_of_lesson_obj(job['lesson'])
            if row is not None:
                self._set_row_state(row, state, None)
            # 下载管理表的状态列也要跟着改
            r = self._task_row_of_job.get(job_id)
            if r is not None and r < self.tbl_tasks.rowCount():
                cur = self.tbl_tasks.item(r, 2)
                if cur is not None:
                    cur.setText(state)
        queued_state = '已暂停' if state == '已暂停' else '排队中'
        for job_id, le, _c, _p, _q in list(self.pending_queue):
            row = self._row_of_lesson_obj(le)
            if row is not None:
                self._set_row_state(row, queued_state, None)

    def _sync_pause_button(self):
        """有任务在跑时才让暂停按钮可用。"""
        busy = bool(self.running_workers) or bool(self.pending_queue)
        self.btn_pause.setEnabled(busy)
        if not busy and self._paused:
            # 全部结束了，自动解除暂停状态
            self._paused = False
            self.control.resume()
            self.btn_pause.setText('暂停')
            self.btn_pause.setObjectName('PauseBtn')
            self._apply_style()

    # ── 兼容入口（旧代码/测试用）────────────────────────────
    def _on_download_ok(self, job_id, msg, out_path):
        """旧的成功回调，转发到统一完成入口。"""
        self._on_download_completed(job_id, True, msg, out_path)

    def _on_download_failed(self, job_id, msg):
        """旧的失败回调，转发到统一完成入口。"""
        self._on_download_completed(job_id, False, msg, '')
    def _set_row_state(self, row, state, msg):
        if row < 0 or self.tbl_lessons.rowCount() <= row:
            return
        item = self.tbl_lessons.item(row, COL_TITLE)
        if not item:
            return
        le = self.lesson_of_row.get(row)
        # ★ 序号在「标题前缀」列，课名列只放纯课名（不按合并行号重编号）
        base = le.title if le else ''
        item.setText(base)
        # ★ 状态词跟在**课名后面**（不是单独一列）——
        #   用户 2026-11-07 指出：状态词本来就是跟着标题的，
        #   用来显示视频文件的下载状态，单独占一列反而看不惯。
        #   存进 STATE_ROLE，委托负责画在课名后面并按状态着色。
        item.setData(STATE_ROLE, state)
        if msg:
            item.setToolTip(msg)

    def _set_both_states(self, job_id, word, msg=None, force=False):
        """同时更新「课程列表状态词」和「下载管理状态列」。

        ★ 为什么必须成对更新（用户 2026-11-07 指出「三处状态要一一对应」）：
          以前只有下载管理表会随阶段变（解析中→下载中→封装中），
          课程列表的状态词一直停在「下载中…」——
          同一节课，列表说在下载、管理表说在封装，对不上号。
          这里保证两处写的**是同一个词**。

        ★ 终态守卫（force=False 时生效）：
          任务已经「已完成 / 失败」之后，**迟到的阶段信号**
          不能把状态改回去（引擎收尾时可能还会补发一次阶段）。
          force=True 用于**写入终态本身**（完成/失败回调），
          此时必须放行 —— 否则终态写不进去。
        """
        job = self.jobs.get(job_id)
        if not job:
            return
        # ① 下载管理表状态列（先读，用来判断是否已是终态）
        r = self._task_row_of_job.get(job_id)
        cur = None
        if r is not None and r < self.tbl_tasks.rowCount():
            cur = self.tbl_tasks.item(r, 2)
        # ★ 已结束的任务，状态列写的是终态（已完成/失败）——
        #   不要被迟到的阶段信号覆盖。
        if not force and job.get('finished') and cur is not None \
                and cur.text() not in PHASE_TEXTS:
            return
        # ② 课程列表（状态词跟在课名后面）
        row = self._row_of_lesson_obj(job.get('lesson'))
        if row is not None:
            self._set_row_state(row, word, msg)
        # ③ 下载管理表状态列
        if cur is not None:
            cur.setText(word)

    # ── 下载管理 ───────────────────────────────────────────
    def _add_task(self, lesson, camp, out_path, state, job_id=None):
        # ★ 若任务表里已经有同一节课（恢复的历史行），**复用那一行**，
        #   不要新增 —— 否则同一节课会出现两行（历史行 + 新行）。
        r = self._find_task_row(out_path)
        if r is None:
            r = self.tbl_tasks.rowCount()
            self.tbl_tasks.insertRow(r)
        else:
            cb0 = self.tbl_tasks.item(r, 0)
            if cb0 is not None:
                cb0.setCheckState(Qt.Checked)

        cb = self.tbl_tasks.item(r, 0)
        if cb is None:
            cb = QTableWidgetItem('')
            cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                        | Qt.ItemIsSelectable)
            self.tbl_tasks.setItem(r, 0, cb)
        cb.setCheckState(Qt.Checked)

        name_item = QTableWidgetItem(lesson.title)
        name_item.setData(Qt.UserRole, out_path)
        name_item.setToolTip(out_path)
        if job_id is not None:
            self._task_row_of_job[job_id] = r
        self.tbl_tasks.setItem(r, 1, name_item)
        self.tbl_tasks.setItem(r, 2, QTableWidgetItem(state))
        self.tbl_tasks.setItem(r, 3, QTableWidgetItem(''))
        self.tbl_tasks.setItem(r, 4, QTableWidgetItem('--'))
        self.tbl_tasks.setItem(r, 5, QTableWidgetItem('--'))

        # ★ 记进下载历史（第二次打开工具时能看到）
        camp_name = getattr(camp, 'name', '') or ''
        self._record_history(out_path, lesson.title, camp=camp_name,
                             state=state, duration=lesson.duration or 0)
        self._flush_history()

    def _find_task_row(self, out_path):
        """按成品路径找任务表里的行号；找不到返回 None。"""
        if not out_path:
            return None
        for r in range(self.tbl_tasks.rowCount()):
            it = self.tbl_tasks.item(r, 1)
            if it is not None and (it.data(Qt.UserRole) or '') == out_path:
                return r
        return None

    def _update_task(self, job_id, state, msg):
        """按 job_id 找到对应任务行并更新状态。

        之前是按课程名匹配 —— 同一个营里两节同名课会更新错行。
        """
        r = self._task_row_of_job.get(job_id)
        if r is None or r >= self.tbl_tasks.rowCount():
            return
        job = self.jobs.get(job_id)
        le = job['lesson'] if job else None
        self.tbl_tasks.setItem(r, 2, QTableWidgetItem(state))
        path = (le.out_path if le else '') or ''
        it = self.tbl_tasks.item(r, 1)
        # 音频可能实际写成了 .m4a，路径要跟着更新
        if os.path.isfile(path):
            mb = os.path.getsize(path) / 1048576.0
            self.tbl_tasks.setItem(r, 3, QTableWidgetItem('%.1f MB' % mb))
            if it:
                it.setData(Qt.UserRole, path)
                it.setToolTip(path)
        self.tbl_tasks.setItem(
            r, 4, QTableWidgetItem('--'))
        # 任务结束：速度归零，剩余时间列改成显示实际用时
        if job is not None:
            job['speed'] = 0.0
            job['rate_dur'] = 0.0
            # ★ 标记为已结束 —— 定时刷新不能再动这一行，
            #   否则「用时 …」会被覆盖回估算值
            job['finished'] = True
            el = job.get('t0')
            spent = (time.time() - el) if el else 0
            self.tbl_tasks.setItem(
                r, 5, QTableWidgetItem('用时 %s' % fmt_dur(spent)))

        # ★ 写进下载历史（记最终大小与状态）
        size = 0
        if path and os.path.isfile(path):
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
        self._record_history(
            path, (le.title if le else ''),
            camp=getattr(job.get('camp') if job else None, 'name', '') or '',
            state=state, size=size,
            down=(job.get('down') if job else 0) or 0,
            total=(job.get('total') if job else 0) or 0,
            done_dur=(job.get('done_dur') if job else 0.0) or 0.0,
            total_dur=(job.get('total_dur') if job else 0.0) or 0.0,
            duration=(le.duration if le else 0) or 0)
        self._flush_history()

    def _checked_tasks(self):
        """任务表中勾选了的行。"""
        out = []
        for r in range(self.tbl_tasks.rowCount()):
            cb = self.tbl_tasks.item(r, 0)
            if cb and cb.checkState() == Qt.Checked:
                it = self.tbl_tasks.item(r, 1)
                if it:
                    out.append((r, it.text(), it.data(Qt.UserRole) or ''))
        return out

    def clear_task_list(self):
        """只清列表，不删文件。

        ★ 历史**也一起清** —— 否则下次打开工具这些记录又会冒出来，
          「清除列表」就失去意义了。
        """
        n = self.tbl_tasks.rowCount()
        self.tbl_tasks.setRowCount(0)
        self.history = {}
        self._flush_history()
        self.log('已清除下载列表（文件保留，历史记录已清）。')

    def delete_task_files(self):
        """删除任务列表中勾选了的成品文件（移到「_已删除」子目录）。"""
        checked = self._checked_tasks()
        if not checked:
            QMessageBox.information(self, '提示', '请先勾选要删除的任务。')
            return
        ans = QMessageBox.question(
            self, '删除文件',
            '将删除 %d 个成品文件。\n\n文件会先移到「_已删除」子目录，确认？'
            % len(checked),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return

        trash = os.path.join(self.out_dir, '_已删除')
        moved = 0
        for r, title, path in checked:
            if path and os.path.isfile(path):
                try:
                    os.makedirs(trash, exist_ok=True)
                    base = os.path.basename(path)
                    stem, ext = os.path.splitext(base)
                    target = os.path.join(trash, base)
                    k = 1
                    while os.path.exists(target):
                        target = os.path.join(trash, '%s-%d%s' % (stem, k, ext))
                        k += 1
                    os.replace(path, target)
                    moved += 1
                except Exception as e:
                    self.log('删除失败 %s：%s' % (path, e))
        self.tbl_tasks.setRowCount(0)
        # ★ 删掉的文件，历史记录也要清 —— 否则列表里还留着已删的条目
        self.history = {}
        self._flush_history()
        self.log('已移动 %d 个文件到 %s' % (moved, trash))
        QMessageBox.information(self, '完成', '已移动 %d 个文件。' % moved)

    # ── 设置 ───────────────────────────────────────────────
    def _on_browse(self):
        d = QFileDialog.getExistingDirectory(self, '选择下载目录',
                                             self.ed_out.text() or default_out_dir())
        if d:
            self.ed_out.setText(d)
            self._save_cfg()

    def _save_cfg(self):
        new_dir = self.ed_out.text().strip()
        changed = (new_dir != self.out_dir)
        self.out_dir = new_dir
        self.quality = self.cmb_quality.currentData() or 'max'
        self.platform_id = self.cmb_platform.currentData()
        save_config({'out_dir': self.out_dir,
                     'quality': self.quality,
                     'platform': self.platform_id})
        groups = self._lesson_groups or (
            [(self.current_camp, self.lessons)] if self.current_camp else [])
        if groups:
            n = self.tbl_lessons.rowCount() or len(self.lessons)
            if len(groups) == 1:
                hint = ('共 %d 节 · 目录：%s'
                        % (n, os.path.join(self.out_dir,
                                          self._camp_folder(groups[0][0]))))
            else:
                hint = ('共 %d 节 · %d 个营 · 各自存到下载目录下的同名文件夹'
                        % (n, len(groups)))
            self.lbl_lesson_hint.setText(hint)
            # 下载目录变了 → 已下载判定要重来（按当前表格里的营分组）
            if changed:
                self.checker.invalidate()
                self._scan_existing(groups)

    # ── 日志 ───────────────────────────────────────────────
    def log(self, text):
        stamp = time.strftime('%H:%M:%S')
        line = '[%s] %s' % (stamp, text)
        self.txt_log.appendPlainText(line)
        self.status_label.setText(text)
        _log_to_file(line)

    def log_state(self, text):
        """只写日志，**不抢底部状态栏**。

        ★ 阶段日志（解析中/下载中/封装中/校验中）每节课要打 4 行，
          每次都覆盖状态栏会让底部的文字不停闪 —— 很难看，
          而且真正重要的信息（完成/失败）会被冲掉。
        """
        stamp = time.strftime('%H:%M:%S')
        line = '[%s] %s' % (stamp, text)
        self.txt_log.appendPlainText(line)
        _log_to_file(line)

    def closeEvent(self, ev):
        # 队列里还没开始的课不再启动（否则窗口关了还在后台下载）
        if self.pending_queue:
            self.log('关闭中：取消 %d 个排队未开始的下载任务。'
                     % len(self.pending_queue))
            self.pending_queue = []
        # ★ 先解除暂停并要求中止 —— 否则暂停中的线程会永远等下去，
        #   窗口关不掉。
        if self.control is not None:
            self.control.resume()
            self.control.stop()
        for w in list(self._scan_workers):
            if w.isRunning():
                w.wait(3000)
        self._scan_workers = []
        for th in self.active_threads:
            if th.isRunning():
                th.wait(3000)
        # ★ 最后再落一次盘 —— 关闭前的最终进度不能丢
        self._flush_history()
        self._save_cfg()
        ev.accept()


# ── 日志文件（可选）──────────────────────────────────────────
# 设置环境变量 XQD_LOG_FILE 后，运行日志会**同时**写到该文件。
# 用途：exe 是 --windowed 打包的，没有控制台；出问题时要能拿到日志。
_LOG_FILE = os.environ.get('XQD_LOG_FILE', '').strip()


def _log_to_file(line):
    if not _LOG_FILE:
        return
    try:
        with open(_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def _fmt_dur(sec):
    try:
        sec = int(sec or 0)
    except Exception:
        return '-'
    if sec <= 0:
        return '-'
    h, m = divmod(sec, 3600)
    m, s = divmod(m, 60)
    if h:
        return '%d:%02d:%02d' % (h, m, s)
    return '%d:%02d' % (m, s)


# ══════════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setStyle('Fusion')
    _apply_cjk_font(app)

    win = MainWindow()
    win.show()

    # 自检/取证开关：设置 XQD_SCREENSHOT=<路径> 时，窗口显示后自动截图并存盘，
    # 然后按 XQD_EXIT_AFTER_SSHOT 的毫秒数退出。
    # 用途：验证打包后的 exe 内部渲染是否正常（外部 PrintWindow 抓帧不可靠）。
    shot_path = os.environ.get('XQD_SCREENSHOT')
    if shot_path:
        def _snap():
            try:
                win.grab().save(shot_path)
                print('screenshot saved:', shot_path)
            except Exception as e:
                print('screenshot failed:', e)
            delay = int(os.environ.get('XQD_EXIT_AFTER_SSHOT', '3000'))
            QTimer.singleShot(delay, app.quit)
        QTimer.singleShot(2500, _snap)

    sys.exit(app.exec())


def _apply_cjk_font(app):
    """确保中文字体可用。

    Qt 在部分环境下（尤其是精简安装 / 容器）拿不到系统字体，
    会把中文渲染成方块。这里显式加载系统里的微软雅黑 / 黑体。
    """
    from PySide6.QtGui import QFont, QFontDatabase
    try:
        families = QFontDatabase.families()
    except Exception:
        families = []
    if any('YaHei' in f or 'SimHei' in f or 'SimSun' in f for f in families):
        return
    for path in (r'C:\Windows\Fonts\msyh.ttc',
                 r'C:\Windows\Fonts\msyhbd.ttc',
                 r'C:\Windows\Fonts\simhei.ttf',
                 r'C:\Windows\Fonts\simsun.ttc'):
        if os.path.isfile(path):
            try:
                QFontDatabase.addApplicationFont(path)
            except Exception:
                pass
    try:
        fams = QFontDatabase.families()
        for name in ('Microsoft YaHei UI', 'Microsoft YaHei', 'SimHei',
                     'SimSun'):
            if name in fams:
                app.setFont(QFont(name, 9))
                return
    except Exception:
        pass


if __name__ == '__main__':
    main()
