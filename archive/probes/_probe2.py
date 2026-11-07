# -*- coding: utf-8 -*-
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd
xqd.connect()
xml = xqd.open_learning()
open('_learn.xml','w',encoding='utf-8').write(xml)
# 按 id 分类统计所有节点
from collections import Counter
c = Counter()
for n in xqd.find_nodes(xml):
    c[n['id'].split('/')[-1]] += 1
print(c)
print('---- 所有非空 text 节点，按 y 排序 ----')
ns = [n for n in xqd.find_nodes(xml) if n['text']]
ns.sort(key=lambda n: (n['y'], n['x']))
for n in ns:
    print('  %-24s x=%-5d y=%-5d w=%-5d h=%-4d %r' % (n['id'].split('/')[-1], n['x'], n['y'], n['w'], n['h'], n['text'][:44]))
