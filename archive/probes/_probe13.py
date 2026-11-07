# -*- coding: utf-8 -*-
import sys, os, re
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
if not xml:
    print('打不开课程列表'); sys.exit(1)
open('_cl.xml','w',encoding='utf-8').write(xml)
root = ET.fromstring(xml)
from collections import Counter
c = Counter(rid(n) for n in root.iter())
print('kind=', xqd.page_kind(xml), 'len=', len(xml))
print(c.most_common(20))
print()
print('--- 有 text 节点（文档顺序，前 70 个）---')
k=0
for n in root.iter():
    t = txt(n)
    if t:
        print('  %-18s %-46s %s' % (rid(n), t[:44], bb(n)))
        k+=1
        if k>=70: break
