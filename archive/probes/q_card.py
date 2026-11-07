# -*- coding: utf-8 -*-
"""找营卡片的可点击父容器，并实测点击进入大课程页。"""
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

# 找所有 clickable=true 的节点，看哪些覆盖该区域
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
        print('  COVER: %-40s %-26s [%d,%d][%d,%d]'
              % (rid.group(1) if rid else '-', cls.group(1) if cls else '-',
                 x1, y1, x2, y2))
