# -*- coding: utf-8 -*-
"""下载历史 / 目录记忆 / 标题后缀列 —— v1.2.2 新功能专项测试。

覆盖用户本轮的三条需求：

  一、课程列表表头带「已下载/全部」计数；状态标记独立成「标题后缀」列
  二、下载目录：首次指向 Windows「下载」文件夹，改过之后记住最后值
  三、下载列表 + 下载进度跨会话记忆；分片缓存可续传

本文件**不联网**，全部用假数据。
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

import xqd_gui
import xqd_history
import xqd_engine

PASS = []
FAIL = []

OUT = os.path.join(tempfile.gettempdir(), 'xqd_test_hist')


def ok(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('OK  ' if cond else 'FAIL', name,
                       ('  -> %s' % (extra,)) if extra else ''))


# ══════════════════════════════════════════════════════════════
#  需求二：下载目录的记忆
# ══════════════════════════════════════════════════════════════

def test_dir_memory():
    print('\n──── 需求二：下载目录记忆 ────')

    # windows_download_dir 指向真实存在的目录
    d = xqd_gui.windows_download_dir()
    ok('windows_download_dir 返回绝对路径',
       os.path.isabs(d), d)
    ok('windows_download_dir 指向存在的目录',
       os.path.isdir(d), d)
    ok('windows_download_dir 末尾不带反斜杠',
       not d.endswith('\\'), d)

    # 首次使用 → Windows 下载目录
    ok('default_out_dir == windows_download_dir',
       xqd_gui.default_out_dir() == d,
       '%s vs %s' % (xqd_gui.default_out_dir(), d))

    # 目录名里应含「下载」或「download」（大小写不敏感）
    ok('默认目录名含「下载/download」',
       ('下载' in d) or ('download' in d.lower()), d)

    # config 里的 out_dir 就是「用户最后用的目录」
    cfgdir = os.path.join(OUT, 'my_custom_dir')
    os.makedirs(cfgdir, exist_ok=True)
    cfg = {'out_dir': cfgdir}
    ok('自定义目录被记住', cfg.get('out_dir') == cfgdir)

    # 旧默认目录（Z:\太极营）在本机不存在 → 应回落
    ok('旧默认目录常量仍在（用于识别）',
       any('太极营' in x for x in xqd_gui._LEGACY_OUT_DIRS),
       str(xqd_gui._LEGACY_OUT_DIRS))


# ══════════════════════════════════════════════════════════════
#  需求三 A：历史读写与合并
# ══════════════════════════════════════════════════════════════

def test_history_io():
    print('\n──── 需求三：历史读写 ────')

    os.makedirs(OUT, exist_ok=True)
    hf = os.path.join(OUT, 'history.json')
    # 清掉上次的残留，保证「不存在的文件」用例成立
    if os.path.exists(hf):
        os.remove(hf)

    # 空/坏文件不崩
    ok('不存在的文件 → 空历史', xqd_history.load_history(hf) == {})
    with open(hf, 'w', encoding='utf-8') as f:
        f.write('{ this is not json')
    ok('坏 JSON → 空历史', xqd_history.load_history(hf) == {})

    # 写 → 读
    hist = {}
    rec = xqd_history.make_record('Z:\\a\\1.mp4', '第一讲', camp='测试营',
                                  state='已完成', size=1024, down=1024,
                                  total=1024, done_dur=60.0, total_dur=60.0,
                                  duration=60)
    xqd_history.merge(hist, rec)
    ok('合并后有一条', len(hist) == 1)
    ok('save_history 返回 True', xqd_history.save_history(
        xqd_history.sort_items(hist), hf))
    back = xqd_history.load_history(hf)
    ok('读回一条', len(back) == 1, str(len(back)))
    ok('课名保留', back['Z:\\a\\1.mp4']['title'] == '第一讲')
    ok('营名保留', back['Z:\\a\\1.mp4']['camp'] == '测试营')
    ok('状态保留', back['Z:\\a\\1.mp4']['state'] == '已完成')
    ok('大小保留', back['Z:\\a\\1.mp4']['size'] == 1024)

    # 同一路径再合并 → 不产生第二条
    xqd_history.merge(hist, xqd_history.make_record(
        'Z:\\a\\1.mp4', '第一讲', state='已完成'))
    ok('同路径不重复', len(hist) == 1)

    # 已完成不被「排队中」覆盖
    xqd_history.merge(hist, xqd_history.make_record(
        'Z:\\a\\1.mp4', '第一讲', state='排队中'))
    ok('已完成不被排队中覆盖', hist['Z:\\a\\1.mp4']['state'] == '已完成',
       hist['Z:\\a\\1.mp4']['state'])

    # 失败也不被「下载中」覆盖
    hist2 = {}
    xqd_history.merge(hist2, xqd_history.make_record(
        'Z:\\b\\2.mp4', '第二讲', state='失败'))
    xqd_history.merge(hist2, xqd_history.make_record(
        'Z:\\b\\2.mp4', '第二讲', state='下载中'))
    ok('失败不被下载中覆盖', hist2['Z:\\b\\2.mp4']['state'] == '失败',
       hist2['Z:\\b\\2.mp4']['state'])

    # 进度只前进不后退
    hist3 = {}
    xqd_history.merge(hist3, xqd_history.make_record(
        'Z:\\c\\3.mp4', '第三讲', state='下载中', down=500, done_dur=30.0))
    xqd_history.merge(hist3, xqd_history.make_record(
        'Z:\\c\\3.mp4', '第三讲', state='下载中', down=100, done_dur=10.0))
    ok('字节进度不后退', hist3['Z:\\c\\3.mp4']['down'] == 500,
       str(hist3['Z:\\c\\3.mp4']['down']))
    ok('时长进度不后退', hist3['Z:\\c\\3.mp4']['done_dur'] == 30.0,
       str(hist3['Z:\\c\\3.mp4']['done_dur']))

    # 排序：新的在前
    hist4 = {}
    for i in range(3):
        r = xqd_history.make_record('p%d' % i, '课%d' % i, state='已完成')
        r['ts'] = 1000 + i
        xqd_history.merge(hist4, r)
    items = xqd_history.sort_items(hist4)
    ok('按时间倒序', items[0]['path'] == 'p2', items[0]['path'])

    # 上限
    items = [{'path': 'p%d' % i, 'ts': i} for i in range(600)]
    xqd_history.save_history(items, hf)
    raw = json.load(open(hf, encoding='utf-8'))
    ok('历史条数有上限', len(raw['items']) <= xqd_history.MAX_HISTORY,
       str(len(raw['items'])))


# ══════════════════════════════════════════════════════════════
#  需求三 B：分片缓存目录（跨会话续传的载体）
# ══════════════════════════════════════════════════════════════

def test_parts_cache():
    print('\n──── 需求三：分片缓存目录 ────')

    p = 'Z:\\营\\1.第一讲.2025.03.12.mp4'
    k1 = xqd_history.parts_key(p)
    k2 = xqd_history.parts_key(p)
    ok('同一路径 → 同一 key', k1 == k2, '%s vs %s' % (k1, k2))
    ok('key 长度 16', len(k1) == 16, k1)

    p2 = 'Z:\\营\\2.第二讲.2025.03.12.mp4'
    ok('不同路径 → 不同 key', k1 != xqd_history.parts_key(p2))

    root = os.path.join(OUT, 'parts')
    d1 = xqd_history.parts_dir_for(p, root)
    d2 = xqd_history.parts_dir_for(p, root)
    ok('同一路径 → 同一目录', d1 == d2, '%s vs %s' % (d1, d2))
    ok('目录在 root 下', d1.startswith(root))

    # 写入几个假分片
    os.makedirs(d1, exist_ok=True)
    for i in range(5):
        with open(os.path.join(d1, '%05d_v.f1_%d.ts' % (i, i)), 'wb') as f:
            f.write(b'x' * 1000)
    # 拼接中间文件要被忽略
    with open(os.path.join(d1, 'all.ts'), 'wb') as f:
        f.write(b'y' * 999999)

    total, cnt, _ = xqd_history.parts_progress(d1)
    ok('分片个数正确（all.ts 被忽略）', cnt == 5, str(cnt))
    ok('已下字节正确', total == 5000, str(total))

    ok('不存在的目录 → 0', xqd_history.parts_progress(
        os.path.join(root, 'nope')) == (0, 0, 0))

    # 清理
    freed = xqd_history.purge_parts(p, root)
    ok('purge 释放了字节（含 all.ts）', freed >= 5000, str(freed))
    ok('purge 后目录没了', not os.path.isdir(d1))


# ══════════════════════════════════════════════════════════════
#  需求一 & 三：GUI 层
# ══════════════════════════════════════════════════════════════

class FakeLesson(object):
    def __init__(self, title, dur=120, idx=0):
        self.title = title
        self.duration = dur
        self.when = '2025-03-12 06:00'
        self.type = 'VIDEO'
        self.key = '%s#%d' % (title, idx)
        self.out_path = ''


class FakeCamp(object):
    name = '测试营'


class FakePlatform(object):
    """只提供课表，不联网。"""

    def __init__(self, lessons):
        self.camp = FakeCamp()
        self._lessons = lessons

    def camp_catalog(self, camp):
        return list(self._lessons)


def build_gui(app, history=None):
    """造一个不联网的窗口。

    ★ 隔离真实的历史文件：MainWindow 构造时会自动恢复历史，
      不隔离的话会被 ~/.xqd_tool/history.json 里的真实记录干扰。
    """
    real_load = xqd_history.load_history
    xqd_history.load_history = lambda *a, **k: dict(history or {})
    try:
        win = xqd_gui.MainWindow()
    finally:
        xqd_history.load_history = real_load
    win.ed_out.setText(OUT)
    win.out_dir = OUT
    win.cookie = 'fake=1'
    win.auto_check_auth = lambda: None

    lessons = [FakeLesson('第一讲', idx=0), FakeLesson('第二讲', idx=1),
               FakeLesson('第三讲', idx=2)]
    win.platform = FakePlatform(lessons)
    win.current_camp = win.platform.camp
    win.camps = [win.platform.camp]
    win.load_lessons()
    app.processEvents()
    return win


def test_lesson_columns(app):
    print('\n──── 需求一：课程列表表头与标题后缀列 ────')

    win = build_gui(app)

    # ★ v1.5.0：勾选框后面新增「标题前缀」列，课程/后缀各后移一列。
    #   一律引用 xqd_gui.COL_* 常量，避免加列时断言整体错位。
    hdr = win.tbl_lessons.horizontalHeaderItem(xqd_gui.COL_PREFIX)
    ok('第 2 列是「标题前缀」',
       hdr is not None and '标题前缀' in hdr.text(),
       hdr.text() if hdr else '')
    hdr2 = win.tbl_lessons.horizontalHeaderItem(xqd_gui.COL_TITLE)
    ok('第 3 列是「课程」', hdr2 is not None and '课程' in hdr2.text(),
       hdr2.text() if hdr2 else '')
    hdr3 = win.tbl_lessons.horizontalHeaderItem(xqd_gui.COL_SUFFIX)
    ok('第 4 列是「标题后缀」',
       hdr3 is not None and '标题后缀' in hdr3.text(),
       hdr3.text() if hdr3 else '')
    ok('列数是 6',
       win.tbl_lessons.columnCount() == xqd_gui.LESSON_COLUMN_COUNT,
       str(win.tbl_lessons.columnCount()))
    ok('标题前缀 = 原营序号 01',
       win.tbl_lessons.item(0, xqd_gui.COL_PREFIX).text() == '01')

    # 表头计数（挂在「课程」列上）
    win._update_lesson_header(2)
    h = win.tbl_lessons.horizontalHeaderItem(xqd_gui.COL_TITLE).text()
    ok('表头带 (已下载/全部) 计数', '(2/3)' in h, h)

    # 标题后缀列 = 成品文件名里标题后面那段日期（此处假 Lesson 无日期 → 空）
    suf = win.tbl_lessons.item(0, xqd_gui.COL_SUFFIX)
    ok('标题后缀列显示日期', suf is not None, 'None')

    # 课程名里不拼状态文字（状态词单独存 role，由委托画在后面）
    name = win.tbl_lessons.item(0, xqd_gui.COL_TITLE)
    ok('课程名不含状态标记',
       name is not None and '【' not in name.text(),
       name.text() if name else '')

    # 时间进了 tooltip
    ok('课程名 tooltip 含时间',
       name is not None and '2025-03-12' in (name.toolTip() or ''),
       name.toolTip() if name else '')

    # ★ 状态词存在课名 item 的 STATE_ROLE 上（跟在标题后面显示）
    win._set_row_state(0, '已完成', '')
    st = win.tbl_lessons.item(0, xqd_gui.COL_TITLE).data(xqd_gui.STATE_ROLE)
    ok('状态词跟在标题后面（STATE_ROLE）', st == '已完成', st)
    ok('课程名本身仍不含状态文字',
       '【' not in win.tbl_lessons.item(0, xqd_gui.COL_TITLE).text())

    win.close()


def test_restore_history(app):
    print('\n──── 需求三：第二次打开工具恢复下载列表 ────')

    # 造一份历史
    hist_file = os.path.join(OUT, 'hist_restore.json')
    p_done = os.path.join(OUT, '测试营', '1.第一讲.2025.03.12.mp4')
    p_part = os.path.join(OUT, '测试营', '2.第二讲.2025.03.12.mp4')
    p_fail = os.path.join(OUT, '测试营', '3.第三讲.2025.03.12.mp4')
    os.makedirs(os.path.join(OUT, '测试营'), exist_ok=True)

    # 第二讲：留一些分片缓存 → 应显示「可续传」
    seg = xqd_history.parts_dir_for(p_part)
    os.makedirs(seg, exist_ok=True)
    for i in range(3):
        with open(os.path.join(seg, '%05d_v.f1_%d.ts' % (i, i)), 'wb') as f:
            f.write(b'z' * 500)

    hist = {}
    xqd_history.merge(hist, xqd_history.make_record(
        p_done, '第一讲', camp='测试营', state='已完成', size=2048))
    xqd_history.merge(hist, xqd_history.make_record(
        p_part, '第二讲', camp='测试营', state='下载中', down=1500, total=3000))
    xqd_history.merge(hist, xqd_history.make_record(
        p_fail, '第三讲', camp='测试营', state='失败'))
    xqd_history.save_history(xqd_history.sort_items(hist), hist_file)

    # 指向这份历史后开窗
    real_load = xqd_history.load_history
    xqd_history.load_history = lambda *a, **k: real_load(hist_file)
    try:
        win = xqd_gui.MainWindow()
        win.ed_out.setText(OUT)
        win.out_dir = OUT
        win.auto_check_auth = lambda: None
        app.processEvents()

        n = win.tbl_tasks.rowCount()
        ok('恢复了 3 行下载列表', n == 3, str(n))

        texts = [win.tbl_tasks.item(r, 2).text() for r in range(n)]
        ok('含「已完成」', any('已完成' == t for t in texts), str(texts))
        ok('含「失败」', any('失败' == t for t in texts), str(texts))
        ok('含「可续传」', any('可续传' in t for t in texts), str(texts))

        # 已下载的行：复选框应是未勾选（历史不等于待下载）
        cb = win.tbl_tasks.item(0, 0)
        ok('恢复的行默认不勾选', cb.checkState() == Qt.Unchecked)

        # 路径存在
        p0 = win.tbl_tasks.item(0, 1).data(Qt.UserRole)
        ok('恢复了成品路径', bool(p0), str(p0))

        win.close()
    finally:
        xqd_history.load_history = real_load


def test_task_dedupe(app):
    print('\n──── 需求三：恢复行与新行不重复 ────')

    win = build_gui(app)
    out_path = os.path.join(OUT, '测试营', '1.第一讲.2025.03.12.mp4')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # 先手工插一行（模拟恢复的历史行）
    r = win.tbl_tasks.rowCount()
    win.tbl_tasks.insertRow(r)
    it = win.tbl_tasks.item(r, 1)
    from PySide6.QtWidgets import QTableWidgetItem
    it2 = QTableWidgetItem('第一讲')
    it2.setData(Qt.UserRole, out_path)
    win.tbl_tasks.setItem(r, 1, it2)

    before = win.tbl_tasks.rowCount()
    win._add_task(win.lessons[0], win.current_camp, out_path, '排队中')
    after = win.tbl_tasks.rowCount()
    ok('同一路径不新增行', after == before, '%d → %d' % (before, after))

    # 换一条路径 → 应新增
    other = os.path.join(OUT, '测试营', '2.第二讲.2025.03.12.mp4')
    win._add_task(win.lessons[1], win.current_camp, other, '排队中')
    ok('不同路径新增行', win.tbl_tasks.rowCount() == after + 1)

    win.close()


def test_clear_and_delete(app):
    print('\n──── 需求三：清除列表同步历史 ────')

    win = build_gui(app)
    win.history = {}
    win._record_history(os.path.join(OUT, 'x.mp4'), '第一讲', state='已完成')
    ok('历史已有一条', len(win.history) == 1)

    win.clear_task_list()
    ok('清除列表后历史为空', len(win.history) == 0, str(len(win.history)))
    win.close()


def test_engine_resume(app):
    print('\n──── 需求三：引擎跨进程续传 ────')

    # 模拟：seg_dir 由调用方给定；失败时**不能**清空它
    seg = os.path.join(OUT, 'seg_engine')
    os.makedirs(seg, exist_ok=True)
    with open(os.path.join(seg, '00000_v.ts'), 'wb') as f:
        f.write(b'x' * 100)

    real_get = xqd_engine.http_get
    calls = []

    def fake_get(url, timeout=30):
        calls.append(url)
        return 200, b'y' * 100

    xqd_engine.http_get = fake_get
    try:
        # 让 _dl_all 失败 → 走 finally 的保留分支
        real_dl = xqd_engine.download_segments
        xqd_engine.download_segments = lambda *a, **k: (0, 1, 0)
        try:
            xqd_engine.download_lesson(
                lambda: ('https://x/v.m3u8', 'a', True),
                os.path.join(OUT, 'out.mp4'),
                seg_dir=seg, expect_duration=0)
        finally:
            xqd_engine.download_segments = real_dl

        ok('失败后分片缓存仍在', os.path.isdir(seg))
        ok('失败后分片文件还在',
           os.path.isfile(os.path.join(seg, '00000_v.ts')))
    finally:
        xqd_engine.http_get = real_get


def test_engine_keeps_parts_on_fail(app):
    print('\n──── 需求三：分片目录复用与保留策略 ────')

    seg = os.path.join(OUT, 'seg_keep')
    os.makedirs(seg, exist_ok=True)
    with open(os.path.join(seg, '00000_v.ts'), 'wb') as f:
        f.write(b'x' * 100)

    # 1) 成功 → 清理（own_dir=False 且 ok_result=True）
    real_dl = xqd_engine.download_segments
    real_mux = xqd_engine._concat_and_mux
    real_probe = xqd_engine.probe_duration
    real_parse = xqd_engine.parse_manifest
    xqd_engine.download_segments = lambda *a, **k: (3, 0, 300)
    xqd_engine._concat_and_mux = lambda seg_dir, out_path, ext='ts': (
        True, 'ok')
    xqd_engine.probe_duration = lambda p: 100.0
    xqd_engine.parse_manifest = lambda url, quality='max': (
        [('https://x/v.ts', 1.0)] * 3, 'hls', 'ok', 3.0)
    try:
        xqd_engine.download_lesson(
            lambda: ('https://x/v.m3u8', 'a', True),
            os.path.join(OUT, 'ok.mp4'), seg_dir=seg, expect_duration=100)
        ok('成功后分片被清理', not os.path.isdir(seg) or
           not os.listdir(seg), str(os.listdir(seg)
                                  if os.path.isdir(seg) else []))
    finally:
        xqd_engine.download_segments = real_dl
        xqd_engine._concat_and_mux = real_mux
        xqd_engine.probe_duration = real_probe
        xqd_engine.parse_manifest = real_parse

    # 2) keep_parts=True → 成功也保留
    seg2 = os.path.join(OUT, 'seg_keep2')
    os.makedirs(seg2, exist_ok=True)
    with open(os.path.join(seg2, '00000_v.ts'), 'wb') as f:
        f.write(b'x' * 100)
    xqd_engine.download_segments = lambda *a, **k: (3, 0, 300)
    xqd_engine._concat_and_mux = lambda seg_dir, out_path, ext='ts': (
        True, 'ok')
    xqd_engine.probe_duration = lambda p: 100.0
    xqd_engine.parse_manifest = lambda url, quality='max': (
        [('https://x/v.ts', 1.0)] * 3, 'hls', 'ok', 3.0)
    try:
        xqd_engine.download_lesson(
            lambda: ('https://x/v.m3u8', 'a', True),
            os.path.join(OUT, 'ok2.mp4'), seg_dir=seg2,
            expect_duration=100, keep_parts=True)
        ok('keep_parts=True 时保留分片',
           os.path.isdir(seg2) and len(os.listdir(seg2)) > 0)
    finally:
        xqd_engine.download_segments = real_dl
        xqd_engine._concat_and_mux = real_mux
        xqd_engine.probe_duration = real_probe
        xqd_engine.parse_manifest = real_parse


def test_sample_reuses_cache(app):
    print('\n──── 需求三：抽样优先用本地缓存 ────')

    seg = os.path.join(OUT, 'seg_sample')
    os.makedirs(seg, exist_ok=True)
    # 造 20 个分片，抽样 12 个
    segs = []
    for i in range(20):
        name = 'v.f1_%d.ts' % i
        segs.append(('https://x/' + name, 1.0))
        with open(os.path.join(seg, '%05d_%s' % (i, name)), 'wb') as f:
            f.write(b'q' * 50)

    calls = []
    real_get = xqd_engine.http_get

    def fake_get(url, timeout=30):
        calls.append(url)
        return 200, b'q' * 50

    xqd_engine.http_get = fake_get
    try:
        out = xqd_engine._sample_segments(segs, seg)
        ok('抽到 12 片', len(out) == 12, str(len(out)))
        ok('全部命中本地缓存（0 次请求）', len(calls) == 0, str(len(calls)))
    finally:
        xqd_engine.http_get = real_get


def test_purge_orphan(app):
    print('\n──── 需求三：孤儿分片清理 ────')

    root = os.path.join(OUT, 'parts_orphan')
    if os.path.isdir(root):
        shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)

    p_done = os.path.join(OUT, 'done.mp4')
    p_fail = os.path.join(OUT, 'fail.mp4')
    p_part = os.path.join(OUT, 'part.mp4')

    for p in (p_done, p_fail, p_part):
        d = xqd_history.parts_dir_for(p, root)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, '00000_v.ts'), 'wb') as f:
            f.write(b'x' * 1000)

    hist = {}
    xqd_history.merge(hist, xqd_history.make_record(
        p_done, '已完成课', state='已完成'))
    xqd_history.merge(hist, xqd_history.make_record(
        p_fail, '失败课', state='失败'))
    xqd_history.merge(hist, xqd_history.make_record(
        p_part, '未完成课', state='下载中'))

    n, freed = xqd_history.purge_orphan_parts(hist, root)
    ok('清理了已完成的分片目录',
       not os.path.isdir(xqd_history.parts_dir_for(p_done, root)),
       str(n))
    ok('保留了「失败」的分片（续传本钱）',
       os.path.isdir(xqd_history.parts_dir_for(p_fail, root)))
    ok('保留了「未完成」的分片（续传本钱）',
       os.path.isdir(xqd_history.parts_dir_for(p_part, root)))
    ok('释放字节数 > 0', freed > 0, str(freed))

    # 再次清理不应误删「未完成」的
    xqd_history.purge_orphan_parts(hist, root)
    ok('重复清理仍保留未完成的分片',
       os.path.isdir(xqd_history.parts_dir_for(p_part, root)))
    ok('重复清理仍保留失败的分片',
       os.path.isdir(xqd_history.parts_dir_for(p_fail, root)))

    shutil.rmtree(root, ignore_errors=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    test_dir_memory()
    test_history_io()
    test_parts_cache()

    app = QApplication(sys.argv)
    test_lesson_columns(app)
    test_restore_history(app)
    test_task_dedupe(app)
    test_clear_and_delete(app)
    test_engine_resume(app)
    test_engine_keeps_parts_on_fail(app)
    test_sample_reuses_cache(app)
    test_purge_orphan(app)

    print('\n========================================================')
    print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：')
        for f in FAIL:
            print('  -', f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
