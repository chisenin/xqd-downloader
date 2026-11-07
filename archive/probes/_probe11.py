# -*- coding: utf-8 -*-
import sys, os, re, time
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd
def rid(n): return (n.get('resource-id') or '').split('/')[-1]
def txt(n): return (n.get('text') or '').strip()
def bb(n):
    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', n.get('bounds') or '')
    return tuple(map(int, m.groups())) if m else None
xqd.connect()
xml = xqd.open_course_list('调和养正太极营')
open('_cl.xml','w',encoding='utf-8').write(xml)
root = ET.fromstring(xml)
print('page_kind=', xqd.page_kind(xml))
# 统计节点 id
from collections import Counter
c = Counter()
for n in root.iter():
    c[rid(n)] += 1
print(c.most_common(30))
print()
print('--- 前 60 个有 text 的节点（文档顺序） ---')
k = 0
for n in root.iter():
    t = txt(n)
    if t:
        print('  %-22s %-42s %s' % (rid(n), t[:40], bb(n)))
        k += 1
        if k > 60: break
