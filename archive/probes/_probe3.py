# -*- coding: utf-8 -*-
import sys, os, io, re
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

def rid(n):
    return n.get('resource-id','').split('/')[-1]

def text(n):
    return (n.get('text') or '').strip()

def parse_camps(xml):
    root = ET.fromstring(xml)
    out = []
    # 找所有 courseShowType，其所在 item 容器内的 title 即营名
    for n in root.iter():
        if rid(n) == 'courseShowType':
            # 向上找 3 层祖先，取 title
            anc = n
            chain = []
            p = n
            for _ in range(6):
                chain.append(p)
                p = None
                break
            # ET 无 parent，手工递归
            out.append((text(n), n.get('bounds')))
    return out

def walk(node, anc):
    r = rid(node)
    t = text(node)
    if r == 'courseShowType':
        titles = [a for a in anc if rid(a) == 'title' and text(a)]
        print('  badge=%-18s title=%s' % (t, [text(a) for a in titles]))
    for c in node:
        walk(c, anc + [node])

xqd.connect()
xml = xqd.open_learning()
print('=== tree walk ===')
walk(ET.fromstring(xml), [])
