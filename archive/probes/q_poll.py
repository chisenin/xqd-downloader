# -*- coding: utf-8 -*-
"""优化验证：轮询清单变化，提前返回。测 10 节的耗时与配对精度。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

xqd.connect()
CAMP = '引气归源太极营'

xml = xqd.ui_dump()
if xqd.page_kind(xml) != 'course_list':
    xml = xqd.open_course_list(CAMP)
xml = xqd.scroll_top(times=30)
cards = xqd.list_cards(xml)
print('可见卡:', [(c['title'][:16], c['when'], c['bx'], c['by']) for c in cards if c['bx']])

done = set()
t0 = time.time()
n = 0
for it in range(10):
    cards = xqd.list_cards(xml)
    tgt = None
    for c in cards:
        if (c['title'], c['when']) in done or not c['title']:
            continue
        if c['bx'] and c['by'] and c['by'] > 320:
            tgt = c
            break
    if not tgt:
        print('无目标，滚动')
        xqd.scroll_down()
        xml = xqd.ui_dump()
        continue
    done.add((tgt['title'], tgt['when']))
    before = xqd.cache_state()
    ts = time.time()
    xqd.tap(tgt['bx'], tgt['by'])
    # 轮询：清单一变就走
    ch = []
    for _ in range(30):
        time.sleep(0.5)
        after = xqd.cache_state()
        ch = [f for f in after if f.startswith('.') and 'hls' in f
              and (f not in before or before[f][0] != after[f][0])]
        if ch:
            break
    t_poll = time.time() - ts
    ids = []
    for f in ch:
        for b in xqd.biz_ids(xqd.read_manifest(f)):
            if b not in ids:
                ids.append(b)
    n += 1
    print('  [%d] %-40s %s  ids=%s  (%.1fs)' %
          (n, tgt['title'][:38], tgt['when'], ids, t_poll))
    xqd.back(1.5)
    xml = xqd.ui_dump()

print('\n总耗时 %.1fs，平均 %.1fs/节' % (time.time() - t0, (time.time() - t0) / max(n, 1)))
print('最终 kind =', xqd.page_kind(xml))
