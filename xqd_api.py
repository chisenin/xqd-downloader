# -*- coding: utf-8 -*-
"""兴趣岛数据源（API 版）—— 不依赖模拟器，直接用 Cookie 调业务网关。

与既有 ADB 数据源（xqd_app.py）保持**相同语义**，以便 xqd_server / ui.html
可以无缝切换：

    list_camps(tab)     -> [{name, badge, type, count}]     tab ∈ 全部/正式营/体验营/轻课
    camp_catalog(camp)  -> [{title, when, index, ...}]
    resolve(camp, item) -> 可直连的 m3u8 URL

与 ADB 路径的关键差异：
  - ADB 需要逐节播放来绑定 fileId（0.7 秒/节）；API 直接给 topicId，
    调用 getCoursePlayUrl 就能拿到播放地址，**整个营一次性解析完**。
  - 因此「sweep」这一步在 API 模式下被完全取代。

端点契约见 _lel/api/qianliao.py 顶部说明，事实依据见 docs/01-已验证事实.md。
"""
import os
import re
import sys
import time
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '_lel', 'api'))

import qianliao as Q          # noqa: E402
import xqd_app as A           # noqa: E402

# tab -> myCourseListV2 的 skyType
#   正式营 -> FINANCIAL（实测 9 个，与 App「正式营」标签一致）
#   体验营 -> INTENTION（实测 1 个）
#   轻课   -> 无（App 内实测为空，**不要探测**）
TAB_SKYTYPE = {
    '正式营': 'FINANCIAL',
    '体验营': 'INTENTION',
    '轻课': None,
    '全部': None,
}

_CLIENT = None
_CAMP_INDEX = {}       # campName -> {campId, periodId, skuType, businessType, businessId}


def client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = Q.QldClient(verbose=False)
    return _CLIENT


def log(msg):
    A.log(msg)


# ── 营列表 ────────────────────────────────────────────────────────

def _fmt_start(ms):
    """startTime 毫秒 -> 'MM.DD HH:MM'（与 App 课程卡片一致的显示格式）。"""
    if not ms:
        return ''
    try:
        dt = datetime.datetime.fromtimestamp(ms / 1000.0)
        return dt.strftime('%m.%d %H:%M')
    except Exception:
        return ''


def _fmt_date(ms):
    """startTime 毫秒 -> 'YYYY.MM.DD'（用于文件名日期后缀）。"""
    if not ms:
        return ''
    try:
        dt = datetime.datetime.fromtimestamp(ms / 1000.0)
        return dt.strftime('%Y.%m.%d')
    except Exception:
        return ''


def list_camps(tab='全部'):
    """列出某标签下的营。返回 [{name, badge, type, count}]。"""
    c = client()
    sky = TAB_SKYTYPE.get(tab)
    camps = []
    if tab == '轻课':
        # App 内已确认「轻课」为空，不再探测
        return []

    td = {'page': {'page': 1, 'size': 200}}
    if sky:
        td['skyType'] = sky
    data = c.api('/gate/course/myCourseListV2', td) or {}
    items = data.get('courses') or []

    # 「全部」= 正式营 + 体验营 + 公开课
    if tab == '全部':
        seen = set()
        for st in ('FINANCIAL', 'INTENTION'):
            d = c.api('/gate/course/myCourseListV2',
                      {'skyType': st, 'page': {'page': 1, 'size': 200}}) or {}
            for x in d.get('courses') or []:
                key = x.get('id')
                if key in seen:
                    continue
                seen.add(key)
                items.append(x)
        # 再补公开课（campId 为空的 OPEN_COURSE）
        d = c.api('/gate/course/myCourseListV2',
                  {'page': {'page': 1, 'size': 200}}) or {}
        for x in d.get('courses') or []:
            key = x.get('id')
            if key in seen:
                continue
            seen.add(key)
            items.append(x)

    _CAMP_INDEX.clear()
    for x in items:
        name = x.get('campName') or ''
        if not name:
            continue
        sku = x.get('skuType') or ''
        if sku == 'FINANCIAL':
            ctype = '正式营'
        elif sku in ('LAUNCH', 'INTENTION'):
            ctype = '体验营'
        else:
            ctype = '公开课'
        total = x.get('courseTotalNum')
        camps.append({
            'name': name,
            'badge': '%s•共%s课' % (ctype, total) if total else ctype,
            'type': ctype,
            'count': total or 0,
        })
        _CAMP_INDEX[name] = {
            'campId': x.get('campId'),
            'periodId': x.get('periodId'),
            'skuType': sku,
            'businessType': x.get('businessType'),
            'businessId': x.get('businessId'),
            'campName': name,
        }
    log('  API 营列表[%s]：%d 个' % (tab, len(camps)))
    return camps


def camp_info(name):
    """取某营的 {campId, periodId, businessType, businessId}。"""
    if name in _CAMP_INDEX:
        return _CAMP_INDEX[name]
    # 缓存未命中 → 重新拉一次列表
    for tab in ('正式营', '体验营', '全部'):
        list_camps(tab)
        if name in _CAMP_INDEX:
            return _CAMP_INDEX[name]
    return {}


# ── 课表 ──────────────────────────────────────────────────────────

def camp_catalog(camp):
    """整营课表。返回 [{title, when, index, topicId, type, duration, roomId}]。

    与 ADB 版语义一致：title=课名，when=日期，index=序号。
    额外带上 topicId / roomId / duration，供后续解析播放地址。
    """
    info = camp_info(camp)
    camp_id = info.get('campId')
    if not camp_id:
        log('  API 课表「%s」：拿不到 campId（可能是公开课）' % camp)
        return []
    data = client().api('/gate/course/playListOfCourse',
                        {'campId': str(camp_id),
                         'onlyCourseCatalogue': True}) or {}
    courses = data.get('courses') or []
    out = []
    for i, c in enumerate(courses):
        out.append({
            'title': c.get('name') or '',
            'when': _fmt_start(c.get('startTime')),
            'date': _fmt_date(c.get('startTime')),
            'index': i,
            'topicId': c.get('topicId'),
            'roomId': c.get('roomId'),
            'type': c.get('type'),
            'duration': c.get('duration'),
            'fileId': c.get('playUrl'),
            'isReplay': c.get('isReplay'),
        })
    log('  API 课表「%s」：%s 节，采到 %d 节'
        % (camp, len(courses), len(out)))
    return out


# ── 播放地址 ──────────────────────────────────────────────────────

def resolve(camp, item):
    """拿某节课的可直连 m3u8 URL。失败返回 None。"""
    info = camp_info(camp)
    camp_id = info.get('campId') or ''
    topic_id = item.get('topicId')
    room_id = item.get('roomId')

    # 公开课没有 campId，用 OPEN_COURSE + periodId
    if not camp_id:
        btype = 'OPEN_COURSE'
        bid = str(info.get('periodId') or '')
    else:
        btype = 'camp'
        bid = str(camp_id)

    if not topic_id and not room_id:
        return None
    try:
        cpu = client().play_url(topic_id, bid, btype, room_id=room_id)
    except Exception as e:
        log('    解析播放地址失败：%s' % e)
        return None
    if not cpu:
        return None
    return cpu.get('playUrl')


def resolve_all(camp, items, progress=None):
    """批量解析播放地址。返回 {index: (url, total_seconds)}。"""
    out = {}
    total = len(items)
    for i, it in enumerate(items):
        url = resolve(camp, it)
        if url:
            out[it['index']] = (url, it.get('duration') or 0)
        if progress:
            progress(i + 1, total, it.get('title') or '')
    return out


# ── 文件命名 ──────────────────────────────────────────────────────

def course_filename(item, seq=None, used=None):
    """按用户约定生成成品文件名。

    格式（对齐用户给的目标样式）::

        <序号>.<课名>.<YYYY.MM.DD>.mp4
        3.【预告课】八段锦二-左右开弓似射雕.2025.12.02.mp4

    - **序号**：营内课表顺序（1 起）。App 的课程列表就是按这个顺序排的，
      带上序号后即使标题重复也能一眼看出先后。
    - **课名**：保留原始标题（含全角冒号），只替换 Windows 非法字符。
    - **日期后缀**：取该节课的 startTime（App 卡片上的日期）。
    - **重名兜底**：极少数情况下（序号+标题+日期仍相同）追加 `-1`、`-2`。

    used 传入该营已占用的文件名集合（小写）时，自动挑一个不冲突的。
    """
    title = A.safe_name(item.get('title') or '') or '未命名'
    if seq is None:
        seq = (item.get('index') or 0) + 1
    date = item.get('date') or ''
    base = '%d.%s' % (seq, title)
    if date:
        base += '.' + date
    name = base + '.mp4'
    if used is not None:
        k = 1
        while name.lower() in used:
            name = '%s-%d.mp4' % (base, k)
            k += 1
        used.add(name.lower())
    return name


# ── 供 xqd_server 使用的统一入口 ──────────────────────────────────

def download_items(camp, items, task_log=None, progress=None,
                    out_root='D:/user/chisenin/Videos'):
    """按 items（[{title, when}]）下载。返回 (ok, fail, skip)。

    与 ADB 版的区别：**不需要 sweep**。每节课现场调 getCoursePlayUrl 拿链接，
    签名天然新鲜（实测 URL 的 t 参数随请求变化）。
    """
    cat = camp_catalog(camp)
    by_title = {}
    for c in cat:
        by_title.setdefault(c['title'], c)

    folder = os.path.join(out_root, A.safe_name(camp))
    os.makedirs(folder, exist_ok=True)

    used = set()
    ok = fail = skip = 0
    total = len(items)
    for i, it in enumerate(items):
        title = it.get('title')
        meta = by_title.get(title)
        out_path = os.path.join(folder, course_filename(meta or it, used=used))

        def note(msg):
            if task_log:
                task_log(msg)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
            note('已存在，跳过：%s' % title)
            skip += 1
            continue

        meta = by_title.get(title)
        if not meta:
            note('课表里找不到：%s' % title)
            fail += 1
            continue

        url = resolve(camp, meta)
        if not url:
            note('拿不到播放地址：%s' % title)
            fail += 1
            continue

        def dg(pct):
            if progress:
                progress(i + pct / 100.0, total, title)

        good, msg, _ = A.download(url, out_path, progress=dg)
        if good:
            ok += 1
            size = os.path.getsize(out_path) / 1048576.0
            note('✓ %s  [%.1fMB] %s' % (title, size, msg))
        else:
            fail += 1
            note('✗ %s  %s' % (title, msg[:160]))
    return ok, fail, skip


if __name__ == '__main__':
    import sys as _s
    tab = _s.argv[1] if len(_s.argv) > 1 else '正式营'
    for c in list_camps(tab):
        print('  %-28s %-16s %s' % (c['name'], c['badge'], c['type']))
    if len(_s.argv) > 2:
        cat = camp_catalog(_s.argv[2])
        print('课表 %d 节：' % len(cat))
        for c in cat[:10]:
            print('  [%2d] %-40s %-12s %s %ss'
                  % (c['index'], c['title'], c['when'], c['type'], c['duration']))
