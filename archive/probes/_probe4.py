# -*- coding: utf-8 -*-
import sys, os, re
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

def rid(n): return n.get('resource-id','').split('/')[-1]
def txt(n): return (n.get('text') or '').strip()
def bnd(n): return n.get('bounds','')

def parse(xml):
    root = ET.fromstring(xml)
    cards = []
    def rec(node, stack):
        # 判定是否为列表项容器：宽度 >= 850 且高度在 150..400
        b = bnd(node)
        m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', b)
        key = None
        if m:
            x1,y1,x2,y2 = map(int, m.groups())
            if (x2-x1) >= 850 and 150 <= (y2-y1) <= 420:
                key = (x1,y1,x2,y2)
        r = rid(node); t = txt(node)
        if r == 'courseShowType':
            cards.append({'key': stack[-1] if stack else key, 'badge': t, 'title': None, 'ty': None})
        if r == 'title' and t:
            # 营名 title：右半区 x>350
            mm = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', b)
            if mm and int(mm.group(1)) >= 350:
                cards.append({'key': stack[-1] if stack else key, 'badge': None, 'title': t, 'ty': b})
        ns = stack + ([key] if key else [])
        for c in node:
            rec(c, ns)
    rec(root, [])
    # 配对：同一 key
    groups = {}
    order = []
    for c in cards:
        k = c['key']
        if k not in groups:
            groups[k] = {'badge': None, 'title': None, 'ty': None}
            order.append(k)
        g = groups[k]
        if c['badge']: g['badge'] = c['badge']
        if c['title']:
            g['title'] = c['title']; g['ty'] = c['ty']
    return [(groups[k], order) for k in order]

xqd.connect()
xml = xqd.open_learning()
groups, order = parse(xml)
print('解析到 %d 张营卡片:' % len(groups))
for g in order:
    d = groups[g]
    print('   %-32s %-16s %s' % (d['title'], d['badge'], d['ty']))
