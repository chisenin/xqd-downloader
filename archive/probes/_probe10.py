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

def items(root):
    """返回 (横滑营列表, 竖向营列表)"""
    horiz, vert = [], []
    def rec(node):
        if rid(node) == 'rv':
            b = bb(node)
            # 竖向主列表：宽900 高>800
            if b and (b[2]-b[0]) >= 850 and (b[3]-b[1]) > 800:
                for c in node:
                    cb = bb(c)
                    if not cb: continue
                    h = cb[3]-cb[1]
                    if (cb[2]-cb[0]) >= 850 and 150 <= h <= 420:
                        title, badge = None, None
                        for d in c.iter():
                            if rid(d)=='courseShowType': badge = txt(d)
                            elif rid(d)=='title' and txt(d) and bb(d) and bb(d)[0] >= 350:
                                title = txt(d)
                        if title:
                            vert.append((title, badge, cb))
            else:
                for c in node:
                    cb = bb(c)
                    if cb and (cb[2]-cb[0]) <= 380 and (cb[3]-cb[1]) > 200:
                        for d in c.iter():
                            if rid(d)=='title' and txt(d):
                                horiz.append((txt(d), cb)); break
        for c in node: rec(c)
    rec(root)
    return horiz, vert

xqd.connect()
xml = xqd.open_learning()
for tab in ['全部','正式营','体验营','轻课']:
    hit = None
    for n in xqd.find_nodes(xml):
        if n['text']==tab and n['id'].endswith('/tv_title') and n['y']<400:
            hit = n; break
    if not hit:
        print('找不到标签', tab); continue
    xqd.tap(hit['cx'], hit['cy'], wait=5)
    xml = xqd.ui_dump()
    h, v = items(ET.fromstring(xml))
    print('\n===== %s ===== 横滑%d 竖向%d' % (tab, len(h), len(v)))
    for t, b in h: print('   [横] %s' % t)
    for t, bd, b in v: print('   [竖] %-30s %s' % (t, bd))
