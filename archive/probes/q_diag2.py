# -*- coding: utf-8 -*-
"""诊断2：
 (a) 完整清单正文里是否含课名/元数据
 (b) 点击【已播过的课】时清单 mtime 是否真的不变
 (c) 播放器左上角「<」能否回到列表页
"""
import sys, time, re
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()

# (a) 完整清单正文
st = S._cache_state()
one = [k for k in st if k.endswith('.hls') and not k.endswith('.m3u8')][0]
txt = S._read_remote_manifest(one)
print('=== 清单 %s (%d bytes) ===' % (one, len(txt)))
print(txt[:900])
print()

# (b) 点已播过的课，看 mtime
xml = S.ui_dump()
print('kind=', S.page_kind(xml))
if S.page_kind(xml) != 'course_list':
    for i in range(6):
        S.adb('shell', 'input keyevent KEYCODE_BACK')
        time.sleep(1.6)
        xml = S.ui_dump()
        if S.page_kind(xml) == 'course_list':
            break
cards = S.list_cards(xml)
print('卡片:', [(c['title'][:24], c['when']) for c in cards])
if cards:
    c = cards[0]
    before = S._cache_state()
    S.adb('shell', 'input tap %d %d' % (c['bx'], c['by']))
    time.sleep(6)
    after = S._cache_state()
    ch = [(f, before.get(f, ('-',))[0], after[f][0])
          for f in after if f.startswith('.') and 'hls' in f
          and f in before and before[f][0] != after[f][0]]
    print('播放后 mtime 变化:', ch)
    newest = sorted([(v[0], k) for k, v in after.items()
                     if k.startswith('.') and 'hls' in k], reverse=True)[:3]
    print('当前最新3个清单:')
    for mt, f in newest:
        print('   %s  %s' % (f, mt))
        for bid in S._biz_ids(S._read_remote_manifest(f)):
            print('       biz=%s' % bid)

    # (c) 左上角「<」
    x2 = S.ui_dump()
    print('\n播放器顶部节点:')
    for n in S.find_nodes(x2):
        if n['y'] < 180:
            t = (n['text'] or '').strip()
            print('   %-24s %-24s (%d,%d) clickable=%s'
                  % (n['id'].split('/')[-1], t[:22], n['x'], n['y'],
                     'yes' if 'clickable="true"' in
                     re.search(r'<node[^>]*bounds="\[%d,%d\]\[%d,%d\]"'
                               % (0, 0, 0, 0), '') else ''))
    print('xml 里有 superplayer_rl_top:', 'superplayer_rl_top' in x2)
    # 找可点击的返回箭头
    for m in re.finditer(r'<node[^>]*>', x2):
        s = m.group(0)
        if 'clickable="true"' in s and 'superplayer' in s:
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', s)
            rid = re.search(r'resource-id="([^"]*)"', s)
            print('   clickable superplayer:', rid.group(1) if rid else '-', b.group(0) if b else '')
