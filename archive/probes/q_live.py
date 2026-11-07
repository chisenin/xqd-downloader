# -*- coding: utf-8 -*-
"""实测：从直播回放页 → 更多 → 目录 → 听课列表（原生 nameTv 列表）
目标：验证「点击列表项 → 清单刷新 → 列表保留 → 直接点下一项」，
从而免去每次返回列表页，把每节耗时压到 ~2 秒。
"""
import sys, time, re
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()

xml = S.ui_dump()
print('kind=', S.page_kind(xml))
print('--- 底部节点 ---')
for n in S.find_nodes(xml):
    t = (n['text'] or '').strip()
    if t and n['y'] > 850:
        print('   %-24s %-30s (%d,%d)' % (n['id'].split('/')[-1], t[:28], n['x'], n['y']))

# 点右下角「更多」
more = [n for n in S.find_nodes(xml) if (n['text'] or '').strip() == '更多']
print('更多:', [(n['x'], n['y']) for n in more])
if more:
    S.adb('shell', 'input tap %d %d' % (more[-1]['x'], more[-1]['y']))
    time.sleep(3)
xml = S.ui_dump()
print('after 更多 kind=', S.page_kind(xml))
for n in S.find_nodes(xml):
    t = (n['text'] or '').strip()
    if t:
        print('   %-24s %-30s (%d,%d)' % (n['id'].split('/')[-1], t[:28], n['x'], n['y']))

# 点「目录」
cat = [n for n in S.find_nodes(xml) if (n['text'] or '').strip() == '目录']
print('目录:', [(n['x'], n['y']) for n in cat])
if cat:
    S.adb('shell', 'input tap %d %d' % (cat[0]['x'], cat[0]['y']))
    time.sleep(4)
xml = S.ui_dump()
print('after 目录 kind=', S.page_kind(xml))
les = [n for n in S.find_nodes(xml) if n['id'].endswith('/nameTv')]
print('听课列表 %d 条:' % len(les))
for n in les[:14]:
    print('   %-44s (%d,%d)' % (n['text'][:42], n['x'], n['y']))
