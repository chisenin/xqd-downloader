# -*- coding: utf-8 -*-
"""逐节核对：check_group 的判定 vs 磁盘上真实存在的文件。

找出「课表里没下过的课，却被判定成 ok（已存在）」的错判。
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import xqd_platform as P
import xqd_dedupe

COOKIE = (
    'rsessionId=<RSESSION_ID>'
    '<RSESSION_ID_TAIL>; '
    'userId=<USER_ID>; cUserId=<C_USER_ID>; '
    'uid=<UID>; '
    'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')

OUT = 'Z:/太极营'


def main():
    plat = P.QianliaoPlatform(cookie=COOKIE)
    ck = xqd_dedupe.ExistingChecker(OUT)

    allcamps = []
    for kind in ('正式营', '体验营'):
        try:
            allcamps.extend(plat.list_camps(kind))
        except Exception as e:
            print('取%s失败: %s' % (kind, e))

    total_false_ok = 0
    total_ok = 0
    for camp in allcamps:
        try:
            les = plat.camp_catalog(camp)
        except Exception as e:
            print('%s 取课表失败: %s' % (camp.name, e))
            continue
        folder = os.path.join(OUT, P.safe_name(camp.name))
        alt = xqd_dedupe.legacy_camp_folders(OUT, camp.name, camp.count)
        on_disk = set()
        for d in [folder] + list(alt):
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if os.path.splitext(fn)[1].lower() in \
                            xqd_dedupe.MEDIA_EXTS:
                        on_disk.add(fn)

        falses = []
        oks = 0
        for le in les:
            stem = P.lesson_stem(le)
            st = ck.check_group(folder, stem, le.duration, alt_folders=alt)
            if st['status'] == 'ok':
                oks += 1
                # 该课对应的规范名文件是否真的在盘上？
                hit = [f for f in st['files'] if f[2]]
                names = {os.path.basename(h[0]) for h in hit}
                # 规范名（不带 -N 后缀）是否在盘上
                canonical = [n for n in names
                             if not any(n.startswith(os.path.splitext(
                                 x)[0] + '-') for x in names)]
                if not canonical:
                    falses.append((stem, sorted(names)))
            elif st['status'] == 'broken':
                falses.append((stem, 'BROKEN:' + st['reason']))
        total_ok += oks
        total_false_ok += len(falses)
        print('%-24s 课%3d  盘%3d  判ok%3d  异常%d'
              % (camp.name, len(les), len(on_disk), oks, len(falses)))
        for s, n in falses[:5]:
            print('      异常: %s  -> %s' % (s, n))
    print('\n合计 ok=%d  异常=%d' % (total_ok, total_false_ok))


if __name__ == '__main__':
    main()
