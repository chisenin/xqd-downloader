# -*- coding: utf-8 -*-
"""极限提速实验：点「去学习」→ 清单刷新 → 立即返回。
测量真实最小耗时，并检查返回后列表位置是否保留（省掉重新定位）。
"""
import sys, time
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()

# 先确保在课程列表页
xml = S.ui_dump()
print('kind=', S.page_kind(xml))
if S.page_kind(xml) != 'course_list':
    for i in range(6):
        S.adb('shell', 'input keyevent KEYCODE_BACK')
        time.sleep(1.6)
        xml = S.ui_dump()
        if S.page_kind(xml) == 'course_list':
            break
    print('-> kind=', S.page_kind(xml))

cards = S.list_cards(xml)
print('卡片 %d:' % len(cards))
for c in cards:
    print('   %-40s %-12s btn=(%s,%s)' % (c['title'][:38], c['when'],
                                          c['bx'], c['by']))

# 连测 4 节：点→等清单→立即返回→重新dump
titles_before = [c['title'] for c in cards]
t_all = time.time()
for i, c in enumerate(cards[:4]):
    if c['bx'] is None:
        continue
    t0 = time.time()
    before = S._cache_state()
    S.adb('shell', 'input tap %d %d' % (c['bx'], c['by']))
    ch, got = [], []
    while time.time() - t0 < 8:
        time.sleep(0.25)
        after = S._cache_state()
        ch = [f for f, st in after.items()
              if f.startswith('.') and f.endswith('.hls')
              and (f not in before or before[f][0] != st[0])]
        if ch:
            break
    t_hit = time.time() - t0
    for f in ch:
        for bid in S._biz_ids(S._read_remote_manifest(f)):
            if bid not in got:
                got.append(bid)
    # 立刻返回
    S.adb('shell', 'input keyevent KEYCODE_BACK')
    time.sleep(1.2)
    xml2 = S.ui_dump()
    t_back = time.time() - t0
    cards2 = S.list_cards(xml2)
    print('  [%d] %-30s 命中%.1fs 返回%.1fs fileId=%s 首卡=%s'
          % (i + 1, (c['title'] or '?')[:28], t_hit, t_back, got,
             cards2[0]['title'][:22] if cards2 else 'N/A'))
print('\n4 节总耗时 %.1fs  (%.2fs/节)' % (time.time() - t_all,
                                        (time.time() - t_all) / 4))
