# -*- coding: utf-8 -*-
"""验证：滚到顶部后逐个点击「去学习」→ 捕获清单差分 → BACK 返回。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

xqd.connect()
xml = xqd.ui_dump()
if xqd.page_kind(xml) != 'course_list':
    xml = xqd.open_course_list('引气归源太极营')
print('kind =', xqd.page_kind(xml))

print('滚到顶部…')
xml = xqd.scroll_top(times=28)
cards = xqd.list_cards(xml)
vis = [c for c in cards if c['bx']]
print('可见 %d / 共 %d' % (len(vis), len(cards)))
for c in vis:
    print('   btn=(%s,%s) %-42s %s' % (c['bx'], c['by'], c['title'][:40], c['when']))

# 选一个不在吸顶区（by>320）的按钮
tgt = None
for c in vis:
    if c['by'] and c['by'] > 320:
        tgt = c
        break
if not tgt:
    print('没有安全目标')
    sys.exit(1)

print('\n点击 → %s (%s)' % (tgt['title'], tgt['when']))
before = xqd.cache_state()
xqd.tap(tgt['bx'], tgt['by'])
time.sleep(8)
xml = xqd.ui_dump()
print('播放后 kind =', xqd.page_kind(xml))
after = xqd.cache_state()
ch = [f for f in after if f.startswith('.') and 'hls' in f
      and (f not in before or before[f][0] != after[f][0])]
print('清单变化 %d:' % len(ch))
for f in ch:
    print('   %-42s %s' % (f, xqd.biz_ids(xqd.read_manifest(f))))

if xqd.page_kind(xml) == 'player':
    les = [n for n in xqd.find_nodes(xml) if n['id'].endswith('/nameTv')]
    print('\n播放器 nameTv %d 条:' % len(les))
    for n in les[:10]:
        print('   %-46s (%d,%d)' % (n['text'][:44], n['x'], n['y']))

print('\nBACK 返回…')
xqd.back(2.5)
xml = xqd.ui_dump()
print('返回后 kind =', xqd.page_kind(xml))
c2 = xqd.list_cards(xml)
print('返回后首卡: %s' % (c2[0]['title'][:40] if c2 else '-'))
