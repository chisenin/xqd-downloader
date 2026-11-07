import export_courses as E
import time

E.connect()

xml = E._open_camp('静坐内观-身心共养计划')
print('kind =', E._page_kind(xml))
xml = E._scroll_days(xml, -1, times=14)
days = [d[0] for d in E._days(xml)]
print('days =', days)

# 找第一个有课的日期
picked = None
for d in days:
    xml2 = E._tap_day(xml, d)
    cs = E._day_cards(xml2)
    if cs:
        picked = (d, cs)
        break
    xml = xml2
print('picked day =', picked[0] if picked else None, 'cards =',
      [c['title'] for c in picked[1]] if picked else None)
if not picked:
    raise SystemExit(1)

d, cs = picked
xml = E.ui_dump()
st0 = E._cache_state()
E.adb('shell', 'input tap %d %d' % (cs[0]['x'], cs[0]['y']))
time.sleep(10)

xml = E.ui_dump()
print('kind =', E._page_kind(xml))
les = E._lesson_nodes(xml)
print('目录课表条目数 =', len(les))
for i, n in enumerate(les):
    print('  [%d] %-44s (%d,%d)' % (i, n['text'][:42], n['x'], n['y']))

st1 = E._cache_state()
print('--- changed ---')
for f in st1:
    if f not in st0 or st0[f] != st1[f]:
        print('   ', f, E._biz_ids(E._read_remote_manifest(f)))
