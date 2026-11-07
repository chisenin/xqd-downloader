# -*- coding: utf-8 -*-
"""实测：WebView 课程列表页 → 逐条「去学习」→ 清单 mtime 差分 → 返回。
目标：测出每节真实耗时，并验证课名↔fileId 配对精度。
"""
import sys, time, re
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import export_courses as E

E.connect()

DATE_RE = re.compile(r'^\d{2}\.\d{2}\s+\d{2}:\d{2}$')


def cards(xml):
    """从 WebView 列表页解析课程卡片。"""
    nodes = E.find_nodes(xml)
    dates = [n for n in nodes if DATE_RE.match((n['text'] or '').strip())]
    out = []
    for d in dates:
        title = ''
        # 课名在日期行上方 ~60-80px，x 在 100..700
        cands = [n for n in nodes
                 if 0 < n['x'] < 700 and d['y'] - 160 < n['y'] < d['y'] - 10
                 and (n['text'] or '').strip()
                 and not DATE_RE.match((n['text'] or '').strip())
                 and (n['text'] or '').strip() not in ('已学完', '未完课', '去学习')]
        if cands:
            cands.sort(key=lambda n: -abs(n['y'] - (d['y'] - 65)))
            title = cands[0]['text'].strip()
        btn = None
        for n in nodes:
            if (n['text'] or '').strip() == '去学习' and 0 < n['y'] - d['y'] < 160:
                btn = n
                break
        out.append({'title': title, 'when': d['text'].strip(),
                    'dx': d['x'], 'dy': d['y'],
                    'bx': btn['x'] if btn else None,
                    'by': btn['y'] if btn else None})
    return out


def back_to_list():
    """返回课程列表页。"""
    for _ in range(4):
        E.adb('shell', 'input keyevent KEYCODE_BACK')
        time.sleep(1.6)
        xml = E.ui_dump()
        if '去学习' in xml and 'toolbarTitle' in xml:
            return xml
    return ''


xml = E.ui_dump()
print('kind=', E._page_kind(xml), ' WebView=', 'WebView' in xml)
cs = cards(xml)
print('当前屏卡片 %d 条:' % len(cs))
for c in cs:
    print('   %-38s %-12s btn=(%s,%s)' % (c['title'][:36], c['when'], c['bx'], c['by']))

# 选前 3 条实测
t0 = time.time()
for i, c in enumerate(cs[:3]):
    if c['bx'] is None:
        continue
    print('\n[%d] %s' % (i + 1, c['title'][:40]))
    before = E._cache_state()
    ta = time.time()
    E.adb('shell', 'input tap %d %d' % (c['bx'], c['by']))
    got, changed = [], []
    for k in range(16):                     # 最多等 8 秒
        time.sleep(0.5)
        after = E._cache_state()
        ch = [f for f, st in after.items()
              if f.startswith('.') and f.endswith('.hls')
              and (f not in before or before[f][0] != st[0])]
        if ch:
            changed = ch
            break
    t_click = time.time() - ta
    for f in changed:
        txt = E._read_remote_manifest(f)
        for bid in E._biz_ids(txt):
            if bid not in got:
                got.append(bid)
    print('    清单更新耗时 %.1fs  changed=%s' % (t_click, changed))
    print('    fileId=%s' % got)
    tb = time.time()
    xml = back_to_list()
    print('    返回耗时 %.1fs  ok=%s' % (time.time() - tb, bool(xml)))
    if xml:
        cs = cards(xml)
print('\n总计 %.1fs / %d 节' % (time.time() - t0, 3))
