# -*- coding: utf-8 -*-
"""恢复 App 到可操作状态：关掉可能的弹窗，回到大课程页或课程列表页。"""
import sys, time
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()
# 先按两次返回清栈
for i in range(3):
    S.adb('shell', 'input keyevent KEYCODE_BACK')
    time.sleep(1.5)
xml = S.ui_dump()
print('after back kind=', S.page_kind(xml), 'len=', len(xml))
if not xml:
    S.launch_app()
    time.sleep(3)
    xml = S.ui_dump()
    print('after launch kind=', S.page_kind(xml), 'len=', len(xml))

for n in S.find_nodes(xml)[:60]:
    t = (n['text'] or '').strip()
    if t:
        print('   %-24s %-38s (%d,%d)' % (n['id'].split('/')[-1], t[:36], n['x'], n['y']))
