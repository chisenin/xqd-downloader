# -*- coding: utf-8 -*-
"""实测：播放器内「目录/听课列表」页签能否直接切课（免返回列表页）。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

xqd.connect()


def show(xml, label):
    nodes = xqd.find_nodes(xml)
    les = [n for n in nodes if n['id'].endswith('/nameTv')]
    print('[%s] kind=%s len=%d nameTv=%d' % (label, xqd.page_kind(xml),
                                               len(xml), len(les)))
    for n in les[:12]:
        print('    %-46s (%d,%d)' % (n['text'][:44], n['x'], n['y']))


xml = xqd.ui_dump()
print('当前 kind =', xqd.page_kind(xml))
if xqd.page_kind(xml) != 'course_list':
    xml = xqd.open_course_list('引气归源太极营')
    print('进入列表 kind =', xqd.page_kind(xml))

cards = xqd.list_cards(xml)
vis = [c for c in cards if c['bx']]
print('可见且有按钮的卡 %d 张' % len(vis))
if not vis:
    print('没有可见卡，先滚一下')
    xqd.scroll_down()
    xml = xqd.ui_dump()
    cards = xqd.list_cards(xml)
    vis = [c for c in cards if c['bx']]
    print('滚后可见 %d 张' % len(vis))

tgt = vis[0]
print('\n点击「去学习」:', tgt['title'], tgt['when'])
before = xqd.cache_state()
xqd.tap(tgt['bx'], tgt['by'], wait=7)
xml = xqd.ui_dump()
print('播放后 kind =', xqd.page_kind(xml))
after = xqd.cache_state()
ch = [f for f in after if f.startswith('.') and 'hls' in f
      and (f not in before or before[f][0] != after[f][0])]
for f in ch:
    print('   变化 %-42s ids=%s' % (f, xqd.biz_ids(xqd.read_manifest(f))))

show(xml, '播放器页')

# 找「目录」页签
print('\n--- 顶部页签候选 ---')
for n in xqd.find_nodes(xml):
    t = n['text']
    if t and n['y'] < 700 and n['y'] > 100:
        print('   %-20s (%d,%d)' % (t[:18], n['x'], n['y']))
