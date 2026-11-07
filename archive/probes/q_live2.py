# -*- coding: utf-8 -*-
"""实测完整链路：直播回放页 → 更多 → 目录 → 听课列表（原生 nameTv）。
并验证：点击列表项后清单是否刷新、列表是否保留（可连续点击）。
"""
import sys, time
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()
xml = S.ui_dump()
print('kind=', S.page_kind(xml))

# 「更多」在右下角
more = [n for n in S.find_nodes(xml) if (n['text'] or '').strip() == '更多']
print('更多:', [(n['x'], n['y']) for n in more])
if not more:
    sys.exit('no 更多')
S.adb('shell', 'input tap %d %d' % (more[-1]['x'], more[-1]['y']))
time.sleep(3)
xml = S.ui_dump()
print('after 更多 kind=', S.page_kind(xml))
for n in S.find_nodes(xml):
    t = (n['text'] or '').strip()
    if t:
        print('   %-24s %-34s (%d,%d)' % (n['id'].split('/')[-1], t[:32], n['x'], n['y']))

cat = [n for n in S.find_nodes(xml) if (n['text'] or '').strip() == '目录']
print('目录:', [(n['x'], n['y']) for n in cat])
if cat:
    S.adb('shell', 'input tap %d %d' % (cat[0]['x'], cat[0]['y']))
    time.sleep(4)
xml = S.ui_dump()
print('after 目录 kind=', S.page_kind(xml))
les = [n for n in S.find_nodes(xml) if n['id'].endswith('/nameTv')]
print('听课列表 %d 条:' % len(les))
for n in les[:15]:
    print('   %-46s (%d,%d)' % (n['text'][:44], n['x'], n['y']))

# 连续点击测试
if les:
    for n in les[:5]:
        t0 = time.time()
        before = S._cache_state()
        S.adb('shell', 'input tap %d %d' % (n['x'], n['y']))
        got, ch = [], []
        while time.time() - t0 < 8:
            time.sleep(0.35)
            after = S._cache_state()
            ch = [f for f, st in after.items()
                  if f.startswith('.') and f.endswith('.hls')
                  and (f not in before or before[f][0] != st[0])]
            if ch:
                break
        for f in ch:
            for bid in S._biz_ids(S._read_remote_manifest(f)):
                if bid not in got:
                    got.append(bid)
        xml2 = S.ui_dump()
        still = len([n for n in S.find_nodes(xml2) if n['id'].endswith('/nameTv')])
        print('  [%-30s] %.1fs fileId=%s 列表仍在=%d条 kind=%s'
              % (n['text'][:28], time.time() - t0, got, still, S.page_kind(xml2)))
