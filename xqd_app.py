# -*- coding: utf-8 -*-
"""兴趣岛课程导出 —— 应用层。

职责划分：
    xqd.py        底层：ADB / 页面识别 / DOM 解析
    xqd_app.py    本文件：业务动作（标签 → 营 → 课表 → 链接 → 下载）
    xqd_server.py 本地 HTTP 服务，把上述动作暴露成 JSON API
    ui.html       前端单页界面

已验证的关键事实：
  · 「学习」页顶部有筛选标签：全部 / 正式营 / 体验营 / 轻课。
    「轻课」实测为空（"暂无内容，去发现更多好课吧！"），无需反复探测。
  · 营卡片 = 竖向 RecyclerView 的直接子项；卡片内
    courseShowType 角标（如 "正式营•共70课"）+ 右侧 title（营名）。
    顶部还有一条横向「继续学」滑块，会与竖向列表重复，需去重。
  · 找营必须先把列表滚到底 —— 首屏只有 3~5 个营。
  · 进入某营的课程列表页（WebView）后，一次 uiautomator dump 就包含
    **整营全部课名**（屏幕外的节点 bounds 为 0，但文本仍可读）。
  · 播放一节课 → App 刷新隐藏清单 `.<md5>.hls` → 清单 URL 里的业务
    fileId 即该节课的视频 fileId。用清单 mtime 差分精确定位。
  · 播放器按一次 BACK 即回课程列表页，滚动位置保留。
  · 清单类型决定下载方式（已实测）：
      · DRM 清单（含 EXT-X-KEY）→ 同目录存在明文孪生 v.fXXXXXXX.m3u8，
        时长与 DRM 清单完全一致（782.4s / 1214.0s 实测吻合），可绕开 DRM。
      · 明文 master 清单（含 EXT-X-STREAM-INF）→ 直接喂给 ffmpeg，
        **不能**用明文孪生（实测孪生是 2.8 小时的其他视频，时长对不上）。
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import xqd                                                    # noqa: E402
import xml.etree.ElementTree as ET                             # noqa: E402

# ── 持久化 ────────────────────────────────────────────────────────
STATE_DIR = os.path.join(HERE, 'state')
NAMES_FILE = os.path.join(STATE_DIR, 'names.json')      # fileId → {name,when,camp}
LINKS_FILE = os.path.join(STATE_DIR, 'links.json')      # fileId → {url, ts, camp}
CATALOG_FILE = os.path.join(STATE_DIR, 'catalog.json')  # camp → [{title,when,index}]
TABS = ['全部', '正式营', '体验营', '轻课']

os.makedirs(STATE_DIR, exist_ok=True)


def _load(path, default):
    return xqd.load_json(path, default)


def _save(path, obj):
    xqd.save_json(path, obj)


def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


# ══════════════════════════ XML 工具 ══════════════════════════

def _rid(node):
    return (node.get('resource-id') or '').split('/')[-1]


def _txt(node):
    return (node.get('text') or '').strip()


def _bb(node):
    m = re.match(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]',
                 node.get('bounds') or '')
    return tuple(int(v) for v in m.groups()) if m else None


def _iter(node):
    for c in node:
        yield c
        for g in _iter(c):
            yield g


# ══════════════════════════ 一、标签与营 ══════════════════════════

def select_tab(tab, tries=3):
    """切到指定筛选标签。返回 dump 后的 XML。"""
    for _ in range(tries):
        xml = xqd.open_learning()
        if not xml:
            continue
        hit = None
        for n in xqd.find_nodes(xml):
            if n['text'] == tab and n['id'].endswith('/tv_title') \
                    and 200 < n['y'] < 400:
                hit = n
                break
        if not hit:
            continue
        # 已选中就不用点（点了会重新加载，反而丢位置）
        sel = 'selected="true"' in ''
        xqd.tap(hit['cx'], hit['cy'], wait=4.5)
        xml = xqd.ui_dump()
        if xqd._is_learn_tab(xml):
            return xml
    return xqd.ui_dump()


def _parse_camps(xml):
    """解析「学习」页 → [(营名, 角标文字)]，去重且保持顺序。"""
    if not xml:
        return []
    root = ET.fromstring(xml)
    camps = []

    def add(name, badge):
        if not name:
            return
        for c in camps:
            if c['name'] == name:
                if badge and not c['badge']:
                    c['badge'] = badge
                return
        camps.append({'name': name, 'badge': badge or ''})

    def rec(node):
        rid = _rid(node)
        if rid == 'rv':
            b = _bb(node)
            vertical = b and (b[2] - b[0]) >= 850 and (b[3] - b[1]) > 800
            for child in node:
                cb = _bb(child)
                if not cb:
                    continue
                w, h = cb[2] - cb[0], cb[3] - cb[1]
                if vertical:
                    if w < 850 or h < 90:
                        continue
                    badge, name = '', None
                    for d in _iter(child):
                        if _rid(d) == 'courseShowType':
                            badge = _txt(d)
                        elif _rid(d) == 'title' and _txt(d):
                            db = _bb(d)
                            # 营名在卡片右半区；分组标题（待学习/已结课）在左窄列
                            if db and db[0] >= 340 and db[2] - db[0] > 120:
                                name = _txt(d)
                                break
                    if name:
                        add(name, badge)
                else:
                    # 顶部横向「继续学」滑块
                    if w > 380 or h < 200:
                        continue
                    for d in _iter(child):
                        if _rid(d) == 'title' and _txt(d):
                            add(_txt(d), '')
                            break
        for c in node:
            rec(c)

    rec(root)
    return camps


def list_camps(tab='全部', scroll=True):
    """列出某标签下的所有营（滚到底采集）。"""
    xml = select_tab(tab)
    seen = []
    seen_names = set()

    def merge(new):
        for c in new:
            if c['name'] not in seen_names:
                seen_names.add(c['name'])
                seen.append(c)

    merge(_parse_camps(xml))
    if scroll:
        stagnant = 0
        for _ in range(40):
            before = len(seen)
            xqd.swipe(450, 1300, 450, 700, 300, wait=1.5)
            xml = xqd.ui_dump()
            if not xqd._is_learn_tab(xml):
                break
            merge(_parse_camps(xml))
            if '没有更多了' in xml:
                break
            if len(seen) == before:
                stagnant += 1
                if stagnant >= 3:
                    break
            else:
                stagnant = 0
    return seen


def _badge_count(badge):
    m = re.search(r'共\s*(\d+)\s*课', badge or '')
    return int(m.group(1)) if m else 0


def _badge_type(badge):
    m = re.match(r'\s*([^\s•]+)', badge or '')
    return m.group(1) if m else ''


# ══════════════════════════ 二、课表 ══════════════════════════

def _cards_from_xml(xml):
    """解析课程列表页 → [{title, when, bx, by, visible}]。

    WebView 一次 dump 就含整营全部课名；屏幕外节点 bounds 为 0。
    卡片文档顺序固定：课名 → 日期 → ▶ → 状态 → 「去学习」按钮。
    """
    if not xml:
        return []
    cards = []
    last_text = ''
    last_date_idx = -99
    for n in xqd.find_nodes(xml):
        t = n['text']
        if not t:
            continue
        if xqd.DATE_RE.match(t):
            cards.append({'title': last_text, 'when': t,
                          'bx': None, 'by': None,
                          'visible': n['y'] > 0, 'index': len(cards)})
            last_date_idx = len(cards) - 1
            last_text = ''
            continue
        if t == '去学习':
            if last_date_idx >= 0 and len(cards) - 1 - last_date_idx <= 12:
                c = cards[last_date_idx]
                if c['bx'] is None and n['y'] > 0:
                    c['bx'], c['by'] = n['cx'], n['cy']
                    c['visible'] = True
            continue
        if t in xqd.STATUS_TEXT or xqd._ICON_RE.match(t):
            continue
        if len(t) > 60:
            continue
        last_text = t
    return cards


def camp_catalog(camp):
    """进入某营的课程列表页，返回 [{title, when, index}] 全量课表。"""
    xml = xqd.open_course_list(camp)
    if not xml:
        return []
    total = xqd.list_total(xml)
    xml = xqd.scroll_top(times=28)
    out, order = [], []
    stagnant = 0
    for _ in range(220):
        cards = _cards_from_xml(xml)
        new = 0
        for c in cards:
            key = (c['title'], c['when'])
            if c['title'] and key not in order:
                order.append(key)
                out.append({'title': c['title'], 'when': c['when'],
                            'index': len(out)})
                new += 1
        if total and len(out) >= total:
            break
        if new == 0:
            stagnant += 1
            if stagnant >= 3:
                break
        else:
            stagnant = 0
        xqd.scroll_down()
        xml = xqd.ui_dump()
        if not xqd.page_kind(xml) == 'course_list':
            break
    log('  课表「%s」：%s 节，采到 %d 节' % (camp, total or '?', len(out)))
    return out


# ══════════════════════════ 三、fileId ↔ 课名 ══════════════════════════

def _manifest_ids(fname):
    txt = xqd.read_manifest(fname)
    return xqd.biz_ids(txt), txt


def play_and_capture(target, before, timeout=25.0):
    """点「去学习」→ 轮询清单刷新 → 返回 (fileId 列表, 清单名列表)。"""
    xqd.tap(target['bx'], target['by'])
    deadline = time.time() + timeout
    changed = []
    while time.time() < deadline:
        time.sleep(0.35)
        after = xqd.cache_state()
        changed = [f for f in after
                   if f.startswith('.') and 'hls' in f
                   and (f not in before or before[f][0] != after[f][0])]
        if changed:
            break
    ids = []
    for f in changed:
        fids, _ = _manifest_ids(f)
        for i in fids:
            if i not in ids:
                ids.append(i)
    return ids, changed


def sweep_camp(camp, progress=None, timeout=25.0):
    """逐节播放，把「课名 → fileId」写进 names.json。

    progress(done, total, title) 用于向前端汇报。
    """
    names = _load(NAMES_FILE, {})
    links = _load(LINKS_FILE, {})
    xml = xqd.open_course_list(camp)
    if not xml:
        log('  (打不开课程列表页)')
        return 0, 0
    xml = xqd.scroll_top(times=28)
    total = xqd.list_total(xml) or 0
    log('  「%s」共 %s 节，开始逐节绑定' % (camp, total or '?'))

    done = set()
    played = newmap = 0
    stagnant = 0
    t0 = time.time()

    while True:
        cards = _cards_from_xml(xml)
        tgt = None
        for c in cards:
            key = (c['title'], c['when'])
            if key in done or not c['title']:
                continue
            if c['bx'] and c['by'] and c['by'] > 320:
                tgt = c
                break
        if not tgt:
            before = [c['when'] for c in cards]
            xqd.scroll_down()
            xml = xqd.ui_dump()
            if xqd.page_kind(xml) != 'course_list':
                log('  (滚动中丢失列表页)')
                break
            if [c['when'] for c in _cards_from_xml(xml)] == before:
                stagnant += 1
                if stagnant >= 3:
                    break
            else:
                stagnant = 0
            continue

        done.add((tgt['title'], tgt['when']))
        played += 1
        before = xqd.cache_state()
        ids, changed = play_and_capture(tgt, before, timeout=timeout)
        for bid in ids:
            if bid not in names:
                names[bid] = {'name': tgt['title'], 'when': tgt['when'],
                              'camp': camp}
                newmap += 1
        # 记录清单 → 链接
        for f in changed:
            fids, txt = _manifest_ids(f)
            m = re.search(r'https?://[^\s"\']+', txt)
            if m and fids:
                links[fids[0]] = {'url': m.group(0), 'ts': time.time(),
                                  'camp': camp}
        if progress:
            progress(played, total, tgt['title'])
        log('  [%d/%s] %-40s → %s'
            % (played, total or '?', tgt['title'][:38],
               ','.join(ids) if ids else '(无)'))

        xqd.back(1.5)
        xml = xqd.ui_dump()
        if xqd.page_kind(xml) != 'course_list':
            xml = xqd.open_course_list(camp)
            if not xml:
                break
            xml = xqd.scroll_top(times=28)
            done = set()

    _save(NAMES_FILE, names)
    _save(LINKS_FILE, links)
    dt = time.time() - t0
    log('  播放 %d 节 / %.0fs，新增映射 %d（累计 %d）'
        % (played, dt, newmap, len(names)))
    return played, newmap


# ══════════════════════════ 四、链接与下载 ══════════════════════════

URL_RE = re.compile(r'https?://[^\s"\']+')

# 同目录明文孪生模板候选（DRM 课专用）
TWIN_RANGES = [(1440280, 1440300)]


def split_dir_query(url):
    """拆 URL → (目录, 文件名, 查询串)。目录含 host/appId/<8hex><biz>/ 三层。"""
    base, _, query = url.partition('?')
    parts = base.rsplit('/', 2)
    if len(parts) < 3:
        return '', '', query
    return parts[0] + '/' + parts[1] + '/', parts[2], query


def query_without(query, drop=('encdomain',)):
    items = [kv for kv in query.split('&')
             if kv and kv.split('=', 1)[0] not in drop]
    return '&'.join(items)


def http_get(url, timeout=25):
    import ssl
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        r = op.open(req, timeout=timeout)
        return r.status, r.read()
    except Exception as e:
        return None, str(e).encode()


def _extinf_total(text):
    return sum(float(x) for x in re.findall(r'#EXTINF:([\d.]+)', text))


def classify_manifest(url):
    """取清单正文并判类型。

    返回 (kind, body_text)
      'master'  多码率 master（含 EXT-X-STREAM-INF）
      'media'   单码率媒体清单
      'drm'     带 EXT-X-KEY 的加密清单
    """
    code, body = http_get(url, timeout=25)
    if code != 200:
        return None, ''
    text = body.decode('utf-8', 'replace')
    if 'EXT-X-STREAM-INF' in text:
        return 'master', text
    if 'EXT-X-KEY' in text:
        return 'drm', text
    return 'media', text


def find_plain_twin(drm_text, url):
    """在 DRM 清单同目录找明文孪生，且要求**总时长一致**才算同源。

    实测：DRM 782.4s ↔ 孪生 782.4s；DRM 1214.0s ↔ 孪生 1214.0s。
    时长校验是必需的 —— 同目录里还有别路的视频（实测有 2.8 小时的其它内容），
    只靠「文件名像模板」会下载到错误的视频。
    """
    directory, _, query = split_dir_query(url)
    if not directory:
        return None
    want = _extinf_total(drm_text)
    if want <= 0:
        return None
    q2 = query_without(query)
    for lo, hi in TWIN_RANGES:
        for n in range(lo, hi):
            name = 'v.f%d.m3u8' % n
            code, body = http_get('%s%s?%s' % (directory, name, q2),
                                  timeout=15)
            if code != 200 or not body.startswith(b'#EXTM3U'):
                continue
            t = body.decode('utf-8', 'replace')
            if 'EXT-X-KEY' in t:
                continue
            got = _extinf_total(t)
            if got > 0 and abs(got - want) < max(1.0, want * 0.005):
                return '%s%s?%s' % (directory, name, q2)
    return None


def safe_name(s, maxlen=90):
    """清理成合法 Windows 文件名。

    保留全角冒号 '：'（用户要求的命名如「先导课：解谜自然之道.mp4」，
    全角冒号在 Windows 与 ffmpeg 中都安全 —— ffmpeg 只把 ASCII ':'
    当分隔符）；只替换 ASCII 非法字符。
    """
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', '_', s).strip().strip('.')
    s = s[:maxlen] or '未命名'
    # Windows 保留设备名
    if s.upper().split('.')[0] in ('CON', 'PRN', 'AUX', 'NUL',
                                   'COM1', 'COM2', 'COM3', 'COM4', 'COM5',
                                   'COM6', 'COM7', 'COM8', 'COM9',
                                   'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5',
                                   'LPT6', 'LPT7', 'LPT8', 'LPT9'):
        s = '_' + s
    return s


def ffmpeg_path():
    p = shutil.which('ffmpeg')
    if p:
        return p
    for c in (r'C:\ffmpeg\bin\ffmpeg.exe',
              r'D:\Program Files\ffmpeg\bin\ffmpeg.exe'):
        if os.path.exists(c):
            return c
    return 'ffmpeg'


def _ff_out_path(out_path):
    """给 ffmpeg 用的临时输出路径 —— 必须以 .mp4 结尾，否则识别不了封装格式。

    （之前用 out_path + '.part' 会让 ffmpeg 报 "Error initializing the muxer"。）
    """
    base = os.path.basename(out_path)
    stem = base[:-4] if base.lower().endswith('.mp4') else base
    return os.path.join(os.path.dirname(out_path), stem + '.part.mp4')


def _pick_variant(text, directory, query):
    """从 master 清单里挑一路子清单（优先 720p 以上的最清晰一路）。

    master 形如：
        #EXT-X-STREAM-INF:...,RESOLUTION=480x852
        video_1440284_0.m3u8?sign=..&t=..
    返回子清单 URL 列表（按分辨率从低到高）。
    """
    out = []
    lines = [l.strip() for l in text.splitlines()]
    for i, l in enumerate(lines):
        if not l.startswith('#EXT-X-STREAM-INF'):
            continue
        res = ''
        m = re.search(r'RESOLUTION=(\d+)x(\d+)', l)
        if m:
            res = '%sx%s' % (m.group(1), m.group(2))
        for j in range(i + 1, len(lines)):
            ref = lines[j]
            if not ref or ref.startswith('#'):
                continue
            url = ref if '?' in ref else ref + '?' + query
            out.append((res, directory + url))
            break
    return out


def download(url, out_path, total_seconds=None, progress=None,
             timeout=3600):
    """下载一节课 → out_path。

    按清单类型分派：
      drm   → 找明文孪生（时长校验）后下载，绕开 DRM
      master→ 取一路子清单下载（显式选码率，避免 ffmpeg 随机选路）
      media → 直接下载
    """
    kind, text = classify_manifest(url)
    if not kind:
        return False, '清单已失效（签名过期），需重新采集链接', 0

    src = url
    note = {'master': '多码率直连', 'media': '明文直连',
            'drm': 'DRM 原链'}[kind]
    dur = _extinf_total(text)

    if kind == 'drm':
        twin = find_plain_twin(text, url)
        if twin:
            src = twin
            note = '明文孪生'
            dur = _extinf_total(http_get(twin, timeout=15)[1]
                                .decode('utf-8', 'replace'))
        else:
            return False, '未找到同源明文孪生，无法导出', 0
    elif kind == 'master':
        directory, _, query = split_dir_query(url)
        variants = _pick_variant(text, directory, query)
        if not variants:
            return False, 'master 清单没有可用码率', 0
        # 这批课多是**竖屏**（480x852 / 720x1280 / 1080x1920），
        # 所以清晰度要看**短边** min(w,h) 而不是高度，否则竖屏课会误选到最差的一路。
        #
        # 选流策略由环境变量 XQD_QUALITY 控制：
        #   'max'（默认）→ 取短边最大的一路（1080x1920）
        #   '720'        → 取短边 >= 720 里最小的一路（720x1280），体积约为 1080p 的 1/2.2
        #   '1080'       → 取短边 >= 1080 里最小的一路
        # 默认 'max'，保证导出画质不降级；如需节省流量/磁盘可设 XQD_QUALITY=720。
        def short_side(res):
            m = re.match(r'(\d+)x(\d+)', res or '')
            if not m:
                return 0
            return min(int(m.group(1)), int(m.group(2)))
        variants.sort(key=lambda v: short_side(v[0]))
        quality = (os.environ.get('XQD_QUALITY') or 'max').strip().lower()
        if quality == 'max':
            pick = variants[-1]
        else:
            try:
                want = int(quality)
            except ValueError:
                want = 720
            pick = None
            for res, u in variants:
                if short_side(res) >= want:
                    pick = (res, u)
                    break
            if not pick:
                pick = variants[-1]
        src = pick[1]
        note = '多码率 %s' % pick[0]
        sub_code, sub_body = http_get(src, timeout=20)
        if sub_code == 200:
            dur = _extinf_total(sub_body.decode('utf-8', 'replace'))

    if not total_seconds:
        total_seconds = dur

    tmp = _ff_out_path(out_path)
    cmd = [ffmpeg_path(), '-y', '-loglevel', 'error',
           '-protocol_whitelist', 'file,http,https,tcp,tls,crypto,httpproxy',
           '-progress', 'pipe:1', '-nostats',
           '-i', src, '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
           '-movflags', '+faststart', tmp]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    except FileNotFoundError:
        return False, '找不到 ffmpeg', 0

    pct = 0.0
    start = time.time()
    try:
        for raw in p.stdout:
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('out_time_ms='):
                continue
            try:
                us = int(line.split('=', 1)[1])
            except ValueError:
                continue
            if total_seconds and total_seconds > 0:
                pct = min(99.5, us / 1e6 / total_seconds * 100)
                if progress:
                    progress(pct)
    except Exception:
        pass
    p.wait(timeout=timeout)

    if p.returncode == 0 and os.path.exists(tmp) \
            and os.path.getsize(tmp) > 100000:
        if os.path.exists(out_path):
            os.remove(out_path)
        os.rename(tmp, out_path)
        return True, note, 100.0
    err = p.stderr.read().decode('utf-8', 'replace')[-300:] \
        if p.stderr else 'rc=%s' % p.returncode
    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
    return False, '%s: %s' % (note, err), pct


def probe_alive(url, timeout=15):
    code, body = http_get(url, timeout=timeout)
    return code == 200 and body.startswith(b'#EXTM3U')


def collect_links_from_cache():
    """从远端隐藏清单收集 {fileId: url}。"""
    out = {}
    st = xqd.cache_state()
    for f in st:
        if not (f.startswith('.') and 'hls' in f):
            continue
        txt = xqd.read_manifest(f)
        m = URL_RE.search(txt)
        if not m:
            continue
        ids = xqd.biz_ids(txt)
        if ids:
            out[ids[0]] = m.group(0)
    return out
