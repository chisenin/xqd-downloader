# -*- coding: utf-8 -*-
import sys, os, re
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

def rid(n): return n.get('resource-id','').split('/')[-1]
def txt(n): return (n.get('text') or '').strip()
def bb(n):
    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', n.get('bounds',''))
    return tuple(map(int, m.groups())) if m else None

def find_all(node, pred, out=None):
    if out is None: out = []
    if pred(node): out.append(node)
    for c in node: find_all(c, pred, out)
    return out

xqd.connect()
xml = xqd.open_learning()
root = ET.fromstring(xml)

# 找所有 courseShowType 的位置，看它属于哪个列表项
print('--- 所有 courseShowType 及其祖先 bounds 链 ---')
for n in find_all(root, lambda x: rid(x)=='courseShowType'):
    # 打印祖先链
    def chain(node, anc):
        for c in node:
            if c is n:
                print('   badge=%-16s  ancestors: %s' % (txt(n), ' < '.join('%s%s' % (rid(a), bb(a)) for a in anc)))
                return True
            if chain(c, anc+[node]): return True
        return False
    chain(root, [])

print()
print('--- 所有 title(x>=350) 及其祖先 bounds 链 ---')
for n in find_all(root, lambda x: rid(x)=='title' and txt(x) and bb(x) and bb(x)[0]>=350):
    def chain2(node, anc):
        for c in node:
            if c is n:
                print('   %-30s ancestors: %s' % (txt(n)[:28], ' < '.join('%s%s' % (rid(a), bb(a)) for a in anc)))
                return True
            if chain2(c, anc+[node]): return True
        return False
    chain2(root, [])
