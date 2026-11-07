import export_courses as E
import re
import time

E.connect()

# 1) 慢速上滑能否回到最顶
print('--- slow drag UP x6 (to top) ---')
for i in range(6):
    E.adb('shell', 'input swipe 450 700 450 1200 1200')
    time.sleep(1.8)

xml = E.ui_dump()
print('after up-drag, texts:')
for n in E.find_nodes(xml):
    t = (n['text'] or '').strip()
    if t and 100 < n['y'] < 700:
        print('   %-42s (%d,%d)' % (t[:40], n['x'], n['y']))
