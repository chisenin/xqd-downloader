# -*- coding: utf-8 -*-
"""验证：点「去学习」→ 播放器页标题能否读到课名；同时看清单变化。"""
import sys, time, re
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import export_courses as E

E.connect()
xml = E.ui_dump()
print('=== before ===')
print('kind=', E._page_kind(xml))
print('cache files:', len([f for f in E._cache_state() if f.startswith('.') and 'hls' in f]))

# 找第一个「去学习」按钮（y > 900）
btns = [n for n in E.find_nodes(xml) if (n['text'] or '').strip() == '去学习']
print('去学习 buttons:', [(n['x'], n['y']) for n in btns])
tgt = None
for n in btns:
    if n['y'] > 900:
        tgt = n
        break
print('tapping', tgt)
before = E._cache_state()
E.adb('shell', 'input tap %d %d' % (tgt['x'], tgt['y']))

# 轮询清单变化，最多 12 秒
changed = []
for i in range(12):
    time.sleep(1.0)
    after = E._cache_state()
    for f, st in after.items():
        if f.startswith('.') and 'hls' in f:
            if f not in before or before[f][0] != st[0]:
                changed.append(f)
    if changed:
        break
print('changed after %.1fs:' % (i + 1), changed)

xml2 = E.ui_dump()
print('=== after ===')
print('kind=', E._page_kind(xml2))
for n in E.find_nodes(xml2):
    t = (n['text'] or '').strip()
    if t:
        print('  %-26s %-46s (%d,%d)' % (n.get('id', '').split('/')[-1], t[:44], n['x'], n['y']))

for f in changed:
    txt = E._read_remote_manifest(f)
    print('--- manifest', f)
    print(txt[:300])
    print('biz ids:', E._biz_ids(txt))
