import export_courses as E
import time

E.connect()

# 退到首页
for _ in range(6):
    xml = E.ui_dump()
    k = E._page_kind(xml)
    if k in ('home', 'learn'):
        break
    E.adb('shell', 'input keyevent KEYCODE_BACK')
    time.sleep(2)

xml = E.ui_dump()
print('kind =', E._page_kind(xml))
print('--- 首页全部文本 ---')
for n in E.find_nodes(xml):
    t = (n['text'] or '').strip()
    if t:
        print('  %-30s %-42s (%d,%d)' % (n.get('id', '').split('/')[-1],
                                          t[:40], n['x'], n['y']))
