# -*- coding: utf-8 -*-
"""完整导航链验证：
   学习大课程列表 → 点营卡片(标题) → 大课程页 → 找「课程」图标 → 课程列表页
"""
import sys, time, re
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()


def dump_texts(xml, tag):
    print('--- %s ---' % tag)
    for n in S.find_nodes(xml):
        t = (n['text'] or '').strip()
        if t:
            print('   %-24s %-40s (%d,%d)'
                  % (n['id'].split('/')[-1], t[:38], n['x'], n['y']))


xml = S.ui_dump()
print('kind=', S.page_kind(xml))

# 1) 找营卡片的可点容器（ViewGroup 覆盖 title）
tgt = None
for n in S.find_nodes(xml):
    if n['id'].endswith('/title') and '调和养正太极营' in n['text']:
        tgt = n
        break
print('title=', tgt)

if tgt:
    for m in re.finditer(r'<node[^>]*>', xml):
        s = m.group(0)
        if 'clickable="true"' not in s:
            continue
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', s)
        if not b:
            continue
        x1, y1, x2, y2 = map(int, b.groups())
        if x1 <= tgt['x'] <= x2 and y1 <= tgt['y'] <= y2:
            # 优先选最贴近 title 的（卡片可能多层）
            print('   cover [%d,%d][%d,%d]' % (x1, y1, x2, y2))
    # 点标题正上方一点（避免点到卡片下半部的"继续学习"）
    S.adb('shell', 'input tap %d %d' % (tgt['x'], tgt['y'] - 30))
    time.sleep(8)
    xml = S.ui_dump()
    print('after tap kind=', S.page_kind(xml))
    dump_texts(xml, '大课程页?')
