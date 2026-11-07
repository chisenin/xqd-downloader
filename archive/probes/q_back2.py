# -*- coding: utf-8 -*-
"""定向测试：从播放器返回课程列表页后，滚动位置是否保留。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep2 as S

S.connect()


def brief(xml):
    k = S.page_kind(xml)
    ds = [n['text'].strip() for n in S.find_nodes(xml)
          if S.DATE_RE.match((n['text'] or '').strip())]
    return k, ds


xml = S.ui_dump()
print('起始 kind =', S.page_kind(xml))
if S.page_kind(xml) != 'course_list':
    xml = S.open_camp_card('引气归源太极营') or ''
    xml = S.open_course_tab() or xml
    print('进入列表 kind =', S.page_kind(xml))

cards = S.list_cards(xml)
print('当前屏 %d 张卡:' % len(cards))
for c in cards:
    print('   %-44s %-12s btn=(%s,%s)' % (c['title'][:42], c['when'],
                                         c['bx'], c['by']))
if not cards:
    sys.exit('no cards')

# 选第 2 张卡（避开顶部可能被状态栏遮挡的悬浮按钮）
tgt = cards[1] if len(cards) > 1 else cards[0]
print('\n→ 点击「去学习」:', tgt['title'], tgt['when'])
before = S._cache_state()
S.adb('shell', 'input tap %d %d' % (tgt['bx'], tgt['by']))
time.sleep(8)
xml = S.ui_dump()
print('播放后 kind =', S.page_kind(xml))
after = S._cache_state()
ch = [f for f in after if f.startswith('.') and 'hls' in f
      and (f not in before or before[f][0] != after[f][0])]
print('清单变化 %d 个: %s' % (len(ch), ch[:5]))
for f in ch:
    print('   fileIds:', S._biz_ids(S._read_remote_manifest(f))[:4])

print('\n→ 按 BACK 返回')
S.adb('shell', 'input keyevent KEYCODE_BACK')
time.sleep(2.5)
xml = S.ui_dump()
k, ds = brief(xml)
print('返回后 kind =', k, ' 日期行 =', ds)
if k == 'course_list':
    for c in S.list_cards(xml):
        print('   %-44s %-12s btn=(%s,%s)' % (c['title'][:42], c['when'],
                                             c['bx'], c['by']))
