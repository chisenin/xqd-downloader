# -*- coding: utf-8 -*-
"""实测方案A：播放器「听课列表」页签内直接切换课程，检测清单刷新。"""
import sys, time
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import export_courses as E

E.connect()

# 进入播放器
xml = E.ui_dump()
print('kind=', E._page_kind(xml))
if E._page_kind(xml) != 'player':
    btns = [n for n in E.find_nodes(xml) if (n['text'] or '').strip() == '去学习']
    if btns:
        E.adb('shell', 'input tap %d %d' % (btns[-1]['x'], btns[-1]['y']))
        time.sleep(5)
        xml = E.ui_dump()
        print('after tap kind=', E._page_kind(xml))

# 切到「目录」页签
tab = [n for n in E.find_nodes(xml) if (n['text'] or '').strip() == '目录']
print('目录 tab:', [(n['x'], n['y']) for n in tab])
if tab:
    E.adb('shell', 'input tap %d %d' % (tab[0]['x'], tab[0]['y']))
    time.sleep(3)
xml = E.ui_dump()
les = [n for n in E.find_nodes(xml) if (n.get('id') or '').endswith('/nameTv')]
print('目录课表 %d 条:' % len(les))
for n in les[:10]:
    print('   ', n['text'][:44], (n['x'], n['y']))

# 逐条点击切换，看清单是否刷新
if les:
    for n in les[:4]:
        t0 = time.time()
        before = E._cache_state()
        E.adb('shell', 'input tap %d %d' % (n['x'], n['y']))
        got, ch = [], []
        for k in range(16):
            time.sleep(0.4)
            after = E._cache_state()
            ch = [f for f, st in after.items()
                  if f.startswith('.') and f.endswith('.hls')
                  and (f not in before or before[f][0] != st[0])]
            if ch:
                break
        for f in ch:
            for bid in E._biz_ids(E._read_remote_manifest(f)):
                if bid not in got:
                    got.append(bid)
        print('  [%s] %.1fs changed=%s fileId=%s' % (n['text'][:22], time.time() - t0, ch, got))
