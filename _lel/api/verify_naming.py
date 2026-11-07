# -*- coding: utf-8 -*-
"""验证新命名规则与 App 课程列表逐条对齐。

依据：用户提供的 App 截图（调和养正太极营 前 4 条）
  1 太极：以阴阳之道，启身心之门   02.25 06:00
  2 第一课 《步法虚实转换》         02.26 06:00
  3 第二课 《左右抱球+变换教程》     02.27 06:00
  4 第三课 《掤捋挤按》              02.28 06:00

断言：
  - API 课表顺序 == App 列表顺序（所以序号前缀有意义）
  - API startTime 格式化后的日期 == App 卡片日期
  - 生成的成品文件名符合 <序号>.<课名>.<YYYY.MM.DD>.mp4

用法: python -u _lel/api/verify_naming.py
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '_lel', 'api'))

import xqd_api as API      # noqa: E402

CAMP = '调和养正太极营'
APP_SEEN = [
    ('太极：以阴阳之道，启身心之门', '02.25 06:00'),
    ('第一课 《步法虚实转换》', '02.26 06:00'),
    ('第二课 《左右抱球+变换教程》', '02.27 06:00'),
    ('第三课 《掤捋挤按》', '02.28 06:00'),
]


def main():
    cat = API.camp_catalog(CAMP)
    used = set()
    ok = True
    print('=== %s：与 App 截图逐条比对 ===' % CAMP)
    for i, (title, when) in enumerate(APP_SEEN):
        if i >= len(cat):
            print('  [缺失] 课表只有 %d 条' % len(cat))
            ok = False
            break
        it = cat[i]
        fn = API.course_filename(it, used=used)
        same = (it['title'] == title and it['when'] == when)
        ok = ok and same
        print('  %s [%d] %-30s when=%-12s -> %s'
              % ('OK  ' if same else 'DIFF', i + 1, it['title'][:28],
                 it['when'], fn))

    # 文件名格式自检
    print()
    print('=== 文件名格式自检（全营 %d 节）===' % len(cat))
    used = set()
    import re
    pat = re.compile(r'^\d+\..+\.\d{4}\.\d{2}\.\d{2}\.mp4$')
    bad = []
    for it in cat:
        fn = API.course_filename(it, used=used)
        if not pat.match(fn):
            bad.append(fn)
    if bad:
        ok = False
        for b in bad[:10]:
            print('  [格式不符]', b)
    else:
        print('  全部符合 <序号>.<课名>.<YYYY.MM.DD>.mp4')

    print()
    print('结论：' + ('全部通过' if ok else '存在差异'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
