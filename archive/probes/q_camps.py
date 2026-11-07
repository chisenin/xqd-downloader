# -*- coding: utf-8 -*-
"""遍历「学习」页所有筛选标签，收集完整营名清单（含课数）。"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

TABS = ['全部', '正式营', '体验营', '轻课']

xqd.connect()
xml = xqd.open_learning()
allcamps = {}

for tab in TABS:
    # 找标签并点击
    hit = None
    for n in xqd.find_nodes(xml):
        if n['text'] == tab and n['id'].endswith('/tv_title') and n['y'] < 400:
            hit = n
            break
    if not hit:
        print('找不到标签:', tab)
        continue
    xqd.tap(hit['cx'], hit['cy'], wait=4)
    xml = xqd.ui_dump()
    print('\n===== 筛选：%s =====' % tab)

    seen = {}
    for i in range(20):
        nodes = xqd.find_nodes(xml)
        # 营名 = id=/title 且 x>150；课数 = id=/courseShowType
        counts = {}
        for n in nodes:
            if n['id'].endswith('/courseShowType'):
                counts[n['text']] = 1
        for n in nodes:
            if n['id'].endswith('/title') and n['x'] > 150 and n['text']:
                seen.setdefault(n['text'], counts.get(n['text'], ''))
        if '没有更多了' in xml:
            break
        xqd.swipe(450, 1300, 450, 700, 300, wait=1.6)
        xml = xqd.ui_dump()
        if xqd.page_kind(xml) not in ('learn_list', 'unknown'):
            break
    for t, c in seen.items():
        allcamps.setdefault(t, c)
    print('  本标签 %d 个营' % len(seen))
    for t, c in seen.items():
        print('     %-34s %s' % (t[:32], c))

print('\n===== 合计 %d 个营 =====' % len(allcamps))
for t, c in allcamps.items():
    print('  %-36s %s' % (t[:34], c))

xqd.save_json(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'camps.json'), allcamps)
