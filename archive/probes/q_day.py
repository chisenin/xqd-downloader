import export_courses as E
import time

E.connect()


def items(xml, suffix):
    return [(n['text'], n['x'], n['y']) for n in E.find_nodes(xml)
            if (n.get('id') or '').endswith(suffix)]


def days(xml):
    return items(xml, '/item_title')


def cards(xml):
    return [t.strip() for t, x, y in items(xml, '/tv_title') if t.strip() != '每日计划']


xml = E.ui_dump()
print('days:', [d[0] for d in days(xml)])

for want in ('第1天', '第2天', '第3天'):
    for t, x, y in days(xml):
        if t == want:
            E.adb('shell', 'input tap %d %d' % (x, y))
            time.sleep(4)
            xml = E.ui_dump()
            print('%s -> cards=%s' % (want, cards(xml)))
            # 打印下半屏全部文本
            for n in E.find_nodes(xml):
                if n['y'] > 1330 and (n['text'] or '').strip():
                    print('     %-22s %-36s' % (n.get('id', '').split('/')[-1],
                                                n['text'][:34]))
            break
