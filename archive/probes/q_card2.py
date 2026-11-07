# -*- coding: utf-8 -*-
"""实测：点营卡片的正确可点目标 → 进入大课程页 → 找到「课程」图标。"""
import sys, time, re
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()
xml = S.ui_dump()
tgt = None
for n in S.find_nodes(xml):
    if n['id'].endswith('/title') and '调和养正太极营' in n['text']:
        tgt = n
        break
print('title node:', tgt)

if tgt:
    covers = []
    for m in re.finditer(r'<node[^>]*>', xml):
        s = m.group(0)
        if 'clickable="true"' not in s:
            continue
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', s)
        rid = re.search(r'resource-id="([^"]*)"', s)
        cls = re.search(r'class="([^"]*)"', s)
        if not b:
            continue
        x1, y1, x2, y2 = map(int, b.groups())
        if x1 <= tgt['x'] <= x2 and y1 <= tgt['y'] <= y2:
            covers.append((rid.group(1) if rid else '-',
                           cls.group(1) if cls else '-', x1, y1, x2, y2))
    for c in covers:
        print('  COVER %-42s %-24s [%d,%d][%d,%d]' % c)
    if covers:
        rid, cls, x1, y1, x2, y2 = covers[0]
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        print('tap cover at', cx, cy)
        S.adb('shell', 'input tap %d %d' % (cx, cy))
        time.sleep(8)
        x2d = S.ui_dump()
        print('after tap kind=', S.page_kind(x2d))
        for n in S.find_nodes(x2d):
            t = (n['text'] or '').strip()
            if t:
                print('   %-26s %-40s (%d,%d)'
                      % (n['id'].split('/')[-1], t[:38], n['x'], n['y']))
