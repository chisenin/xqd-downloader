# -*- coding: utf-8 -*-
"""兴趣岛课程导出 —— 采集模块。

核心洞察（用户实测 + 验证）：
  路径 = 首页 →「学习」大课程列表 → 点大课程名 → 大课程页 → 点「课程」图标
         → 完整课程列表页（WebView）→ 每条卡片有「课名 / 日期 / 去学习」

  · 进入课程列表页时，**全部课名一次性可见**（滚动即得），无需靠播放反推。
  · 播放器里按一次 BACK 即回到课程列表页，且**滚动位置保留**。
  · 播放一节课 → App 刷新隐藏清单 `.<md5>.hls` → 清单 URL 里的业务 fileId
    就是这节课的视频 fileId。

本模块负责：把某个营的完整课表（课名 + 日期 + 按钮坐标）采集下来。
"""
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ADB = r'D:\Program Files\Netease\MuMu\nx_main\adb.exe'
DEVICE = '192.168.1.101:5555'
PKG = 'com.qlchat.xingqudao'
REMOTE = ('/sdcard/Android/data/%s/files/PlayerCache/txcache' % PKG)
CACHE = os.path.join(HERE, '.cache')
NAMES_FILE = os.path.join(HERE, 'course_names.json')
COURSE_DIR = os.path.join(HERE, 'courses.json')

DATE_RE = re.compile(r'^\d{2}\.\d{2}\s+\d{2}:\d{2}$')

# 状态/按钮类文案 —— 不能当课名
STATUS_TEXT = set([
    '已学完', '已完课', '未完课', '去学习', '正序', '最近学习', '分享',
    '听课进度', '今日课程', '全部', '联系老师', '排行榜', '排名第1名',
    '正在直播', '课程回放中', '已结束', '直播中', '开始上课', '预约',
    '开启消息通知，不错过上课提醒、点评等消息去开启',
])

# 纯图标/私用区字符
_ICON_RE = re.compile(r'^[\ue000-\uf8ff-‏﻿\s]+$')

os.makedirs(CACHE, exist_ok=True)


# ────────────────────────────── 底层 ──────────────────────────────

def sh(args, timeout=60):
    env = dict(os.environ)
    env['MSYS_NO_PATHCONV'] = '1'
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, env=env)
        out = p.stdout.decode('utf-8', 'replace')
        err = p.stderr.decode('utf-8', 'replace')
        return p.returncode, out, err
    except subprocess.TimeoutExpired:
        return -1, '', 'timeout'


def adb(*args, **kw):
    timeout = kw.pop('timeout', 90)
    return sh([ADB, '-s', DEVICE] + list(args), timeout=timeout)


def connect():
    adb('connect', DEVICE, timeout=30)
    time.sleep(1)


def ui_dump():
    """uiautomator dump → 本地文本。"""
    remote = '/sdcard/_xqd_ui_%d.xml' % int(time.time() * 1000 % 100000000)
    adb('shell', 'uiautomator dump %s' % remote, timeout=90)
    local = os.path.join(CACHE, '_ui.xml')
    if os.path.exists(local):
        try:
            os.remove(local)
        except OSError:
            pass
    adb('pull', remote, local, timeout=90)
    if not os.path.exists(local):
        return ''
    try:
        return io.open(local, encoding='utf-8', errors='replace').read()
    except OSError:
        return ''


BOUNDS_RE = re.compile(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')
NODE_RE = re.compile(r'<node[^>]*/?>')


def find_nodes(xml, want_text=None):
    """解析 uiautomator XML → [{'id','text','x','y'}]（x,y 为左上角）。"""
    out = []
    if not xml:
        return out
    for m in NODE_RE.finditer(xml):
        s = m.group(0)
        tm = re.search(r'text="([^"]*)"', s)
        text = tm.group(1) if tm else ''
        if want_text is not None and text != want_text:
            continue
        im = re.search(r'resource-id="([^"]*)"', s)
        rid = im.group(1) if im else ''
        bm = BOUNDS_RE.search(s)
        if not bm:
            continue
        x1, y1, x2, y2 = (int(v) for v in bm.groups())
        out.append({'id': rid, 'text': text.strip(),
                    'x': x1, 'y': y1, 'cx': (x1 + x2) // 2, 'cy': (y1 + y2) // 2,
                    'w': x2 - x1, 'h': y2 - y1})
    return out


def tap(x, y, wait=0.0):
    adb('shell', 'input tap %d %d' % (x, y), timeout=30)
    if wait:
        time.sleep(wait)


def back(wait=1.8):
    adb('shell', 'input keyevent KEYCODE_BACK', timeout=30)
    time.sleep(wait)


def swipe(x1, y1, x2, y2, ms=1200, wait=1.6):
    adb('shell', 'input swipe %d %d %d %d %d' % (x1, y1, x2, y2, ms), timeout=60)
    time.sleep(wait)


# ────────────────────────────── 页面识别 ──────────────────────────────

def page_kind(xml):
    if not xml:
        return 'empty'
    if 'superPlayerView' in xml or 'superplayer_tv_current' in xml:
        return 'player'
    if 'nameTv' in xml and 'startTimeTv' in xml:
        return 'player'               # 播放器「听课列表」
    if 'toolbarTitle' in xml and '去学习' in xml:
        return 'course_list'          # 完整课程列表页（WebView）
    if '全部 ' in xml or '已完课 ' in xml:
        return 'course_list'
    if _is_learn_tab(xml):
        return 'learn_list'           # 「学习」大课程列表页
    if 'messageContent' in xml:
        return 'chat'
    return 'unknown'


# 「学习」页的特征：顶部筛选标签组（全部/正式营/体验营/轻课）
LEARN_TABS = ('全部', '正式营', '体验营', '轻课')


def _is_learn_tab(xml):
    """是否为「学习」页 —— 用筛选标签组判定（比卡片判定可靠，空标签时仍成立）。"""
    if 'tv_title' not in xml:
        return False
    hit = 0
    for t in LEARN_TABS:
        if re.search(r'text="%s"' % t, xml):
            hit += 1
    return hit >= 3


def launch_app():
    adb('shell', 'monkey -p %s -c android.intent.category.LAUNCHER 1' % PKG,
        timeout=60)
    time.sleep(7)


def wake_app():
    """确保 App 在前台，返回当前 XML。"""
    xml = ui_dump()
    k = page_kind(xml)
    if k in ('empty', 'desktop', 'unknown'):
        launch_app()
        xml = ui_dump()
    return xml


def open_learning():
    """进入「学习」大课程列表页。"""
    for _ in range(10):
        xml = ui_dump()
        k = page_kind(xml)
        if 'learn_list' == k or (k == 'unknown' and _learn_cards(xml)):
            return xml
        tabs = [n for n in find_nodes(xml, want_text='学习') if n['y'] > 1400]
        if tabs:
            tap(tabs[0]['cx'], tabs[0]['cy'], wait=4)
            continue
        if k in ('empty', 'desktop'):
            launch_app()
            time.sleep(2)
            continue
        back(2.5)
    return ui_dump()


def _learn_cards(xml):
    """「学习」页的营卡片（标题控件）。

    营名在卡片**右半区**（x>=340）；左侧 x<150 的是分组标题
    （「待学习」「已结课」），不能当营名。
    """
    out = []
    for n in find_nodes(xml):
        if n['id'].endswith('/title') and n['x'] >= 340 and n['text'] \
                and n['w'] > 120:
            out.append(n)
    return out


def camp_cards(xml):
    out = []
    for n in _learn_cards(xml):
        out.append((n['text'], n['x'], n['y']))
    return out


LEARN_TAB_NAMES = ('全部', '正式营', '体验营', '轻课')


def _switch_tab(xml, tab):
    """切到指定筛选标签。返回新 XML。"""
    hit = None
    for n in find_nodes(xml):
        if n['text'] == tab and n['id'].endswith('/tv_title') \
                and 200 < n['y'] < 400:
            hit = n
            break
    if not hit:
        return xml
    tap(hit['cx'], hit['cy'], wait=4.5)
    return ui_dump()


def _find_camp_in_list(xml, camp_name, tries=30):
    """在当前标签页的列表里找营，返回 (x, y) 或 None。"""
    for t, x, y in camp_cards(xml):
        if camp_name in t:
            return (x, y)
    for _ in range(tries):
        if '没有更多了' in xml:
            break
        swipe(450, 1300, 450, 700, 300, wait=1.6)
        xml = ui_dump()
        if page_kind(xml) != 'learn_list':
            break
        for t, x, y in camp_cards(xml):
            if camp_name in t:
                return (x, y)
    return None


def open_camp_card(camp_name, tabs=None):
    """进入指定营的【大课程页】（含「课程」图标）。返回 XML 或 ''。

    营可能只出现在某个筛选标签下（例：「道门-柔筋活络太极营-2营」
    只在「体验营」里），所以要**跨标签**逐个找。
    """
    tabs = tabs or LEARN_TAB_NAMES
    for attempt in range(2):
        xml = open_learning()
        if not xml:
            continue
        tgt = None
        for tab in tabs:
            xml = _switch_tab(xml, tab)
            if page_kind(xml) != 'learn_list':
                xml = open_learning()
                if not xml:
                    continue
            tgt = _find_camp_in_list(xml, camp_name)
            if tgt:
                break
        if not tgt:
            print('    (未找到营：%s)' % camp_name)
            for _ in range(20):
                swipe(450, 700, 450, 1300, 300, wait=1.1)
            continue
        print('    进入大课程页：%s' % camp_name)
        tap(tgt[0], tgt[1] - 30, wait=8)
        xml = ui_dump()
        if 'tvName' in xml:
            return xml
        print('    (未进大课程页，重试)')
        back(3)
    return ''


def open_course_tab():
    """在大课程页点「课程」图标 → 完整课程列表页。"""
    for _ in range(8):
        xml = ui_dump()
        nodes = find_nodes(xml)
        hit = None
        for n in nodes:
            if n['text'].strip() == '课程':
                hit = n
                break
        if hit:
            tap(hit['cx'], hit['cy'], wait=5)
            x2 = ui_dump()
            if page_kind(x2) == 'course_list':
                return x2
            xml = x2
            continue
        # 兜底：找 tvName / course 相关 id
        for n in nodes:
            if re.search(r'(tvName|course|Course)', n['id']):
                tap(n['cx'], n['cy'], wait=5)
                x2 = ui_dump()
                if page_kind(x2) == 'course_list':
                    return x2
                xml = x2
                break
        else:
            return ''
        swipe(450, 1300, 450, 800, 300, wait=2.5)
    return ''


def open_course_list(camp_name):
    """一步到位：进入某营的完整课程列表页。"""
    xml = open_camp_card(camp_name)
    if not xml:
        return ''
    xml = open_course_tab()
    if not xml:
        print('    (未找到「课程」图标)')
    return xml


# ────────────────────────────── 课程列表解析 ──────────────────────────────

def list_total(xml):
    for n in find_nodes(xml):
        m = re.match(r'^全部\s*(\d+)$', n['text'])
        if m:
            return int(m.group(1))
    return 0


def list_cards(xml):
    """解析课程列表页的全部课程卡片（按文档顺序）。

    实测：WebView 一次 uiautomator dump 就包含**整页**（70 节）的 DOM，
    不需要滚动 —— 只是屏幕外的节点 bounds 为 [0,0][0,0]（不可直接点）。
    卡片在文档中的顺序固定为：
        课名 → 日期 → ▶图标 → 状态 → 「去学习」按钮
    因此按文档顺序扫描即可把课名/日期/按钮配对。

    返回 [{'title','when','bx','by','visible','index'}]
    visible=False 表示该卡当前在屏幕外（bounds 为 0），需滚动后才能点。
    """
    nodes = find_nodes(xml)
    cards = []
    last_text = ''          # 最近一个像课名的文本
    last_date_idx = -99     # 最近一个日期节点在 cards 中的下标

    for i, n in enumerate(nodes):
        t = n['text']
        if not t:
            continue
        if DATE_RE.match(t):
            cards.append({
                'title': last_text, 'when': t,
                'dx': n['x'], 'dy': n['y'], 'bx': None, 'by': None,
                'visible': n['y'] > 0, 'index': len(cards),
            })
            last_date_idx = len(cards) - 1
            last_text = ''
            continue
        if t == '去学习':
            # 归属于最近的日期卡片（限定 12 个节点内，避免误配悬浮按钮）
            if last_date_idx >= 0 and len(cards) - 1 - last_date_idx <= 12:
                c = cards[last_date_idx]
                if c['bx'] is None and n['y'] > 0:
                    c['bx'], c['by'] = n['cx'], n['cy']
                    c['visible'] = True
            continue
        if t in STATUS_TEXT or _ICON_RE.match(t):
            continue
        if len(t) > 60:                 # 横幅/提示文案，不是课名
            continue
        last_text = t

    return cards


def scroll_top(times=26):
    """慢速上滚到列表顶部（WebView 只认慢速拖动）。"""
    for _ in range(times):
        swipe(450, 700, 450, 1250, 1200, wait=1.2)
    return ui_dump()


def scroll_down(wait=1.6):
    swipe(450, 1250, 450, 700, 1200, wait=wait)


def collect_catalog(camp_name, verbose=True):
    """采集整个营的完整课表。

    返回 [{'title','when','index'}]，按列表顺序。
    """
    xml = open_course_list(camp_name)
    if not xml:
        return []
    total = list_total(xml)
    if verbose:
        print('  该营共 %s 节' % (total or '?'))
    xml = scroll_top()
    seen = {}
    order = []
    stagnant = 0
    for _ in range(200):
        cards = list_cards(xml)
        new = 0
        for c in cards:
            key = (c['title'], c['when'])
            if key not in seen:
                seen[key] = c
                order.append({'title': c['title'], 'when': c['when']})
                new += 1
        if verbose:
            print('    屏内 %d 张，累计 %d/%s' % (len(cards), len(order),
                                                 total or '?'))
        if new == 0:
            stagnant += 1
            if stagnant >= 3:
                break
        else:
            stagnant = 0
        if total and len(order) >= total:
            break
        scroll_down()
        xml = ui_dump()
        if page_kind(xml) != 'course_list':
            print('    (滚动中丢失列表页)')
            break
    if verbose:
        print('  采集到 %d 节' % len(order))
    return order


# ────────────────────────────── 清单 / fileId ──────────────────────────────

def cache_state():
    """远端隐藏清单 {文件名: (mtime串, size)}。

    Android `ls -la --full-time` 输出形如：
      -rw-rw---- 1 u0_a52 ext_data_rw 1418 2026-11-07 02:16:06.770276400 +0800 .xxx.hls
    """
    r = adb('shell', "ls -la --full-time '%s' 2>/dev/null" % REMOTE, timeout=120)
    st = {}
    for line in (r[1] or '').replace('\r', '').splitlines():
        parts = line.split()
        # 权限 链接数 属主 组 大小 日期 时间 时区 文件名
        if len(parts) < 9 or not parts[0].startswith('-'):
            continue
        st[parts[8]] = (parts[5] + ' ' + parts[6], int(parts[4]))
    return st


def read_manifest(fname):
    r = adb('shell', "cat '%s/%s' 2>/dev/null" % (REMOTE, fname), timeout=60)
    return r[1] or ''


def biz_ids(text):
    """从清单正文提取业务 fileId。"""
    ids = []
    for m in re.finditer(r'/([0-9a-f]{8})(\d{10,})/', text):
        if m.group(2) not in ids:
            ids.append(m.group(2))
    for m in re.finditer(r'"fileId"\s*:\s*"?(\d{15,25})', text):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        return json.load(io.open(path, encoding='utf-8'))
    except (ValueError, OSError):
        return default


def save_json(path, obj):
    io.open(path, 'w', encoding='utf-8').write(
        json.dumps(obj, ensure_ascii=False, indent=1))
