import export_courses as E
import time

E.connect()

cat = E._player_catalog('静坐内观')
print('catalog size =', len(cat))
for t, w, x, y in cat:
    print('   %-46s %-18s (%d,%d)' % (t[:44], w, x, y))

# 试着点第 2 个条目，看能否播放并产生新清单
if len(cat) >= 2:
    t, w, x, y = cat[1]
    before = E._cache_state()
    E.adb('shell', 'input tap %d %d' % (x, y))
    time.sleep(10)
    xml = E.ui_dump()
    print('kind after tap =', E._page_kind(xml))
    after = E._cache_state()
    print('--- changed ---')
    for f in after:
        if f not in before or before[f] != after[f]:
            print('   ', f, E._biz_ids(E._read_remote_manifest(f)))
