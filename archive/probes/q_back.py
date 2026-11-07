# -*- coding: utf-8 -*-
"""诊断：点击「去学习」→ 返回 后到底停在哪一页。"""
import sys, time
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()
xml = S.ui_dump()
print('kind=', S.page_kind(xml))
if S.page_kind(xml) != 'course_list':
    print('先回到列表页')
    for i in range(8):
        S.adb('shell', 'input keyevent KEYCODE_BACK')
        time.sleep(1.8)
        xml = S.ui_dump()
        print('  back->', S.page_kind(xml))
        if S.page_kind(xml) == 'course_list':
            break

cards = S.list_cards(xml)
print('卡片:', [(c['title'][:20], c['when']) for c in cards])
if not cards:
    sys.exit('no cards')
c = cards[0]
print('点击:', c['title'], c['bx'], c['by'])
S.adb('shell', 'input tap %d %d' % (c['bx'], c['by']))
time.sleep(6)
xml = S.ui_dump()
print('播放页 kind=', S.page_kind(xml))
for n in S.find_nodes(xml):
    t = (n['text'] or '').strip()
    if t and n['y'] < 200:
        print('   top: %-22s %-36s (%d,%d)' % (n['id'].split('/')[-1], t[:34], n['x'], n['y']))

for i in range(4):
    S.adb('shell', 'input keyevent KEYCODE_BACK')
    time.sleep(2.0)
    xml = S.ui_dump()
    print('back %d -> kind=%s len=%d' % (i + 1, S.page_kind(xml), len(xml)))
    if S.page_kind(xml) == 'course_list':
        break
    for n in S.find_nodes(xml)[:25]:
        t = (n['text'] or '').strip()
        if t:
            print('      %-22s %-34s (%d,%d)'
                  % (n['id'].split('/')[-1], t[:32], n['x'], n['y']))
