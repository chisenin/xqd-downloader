# -*- coding: utf-8 -*-
"""实时评估：哪些课已完成、哪些缺失、哪些残缺。

直接调业务 API 拿最新课表（不依赖缓存），再与 Z 盘实际文件比对。
输出 JSON 供下载驱动使用。
"""
import os
import sys
import json
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import xqd_dedupe
import xqd_platform as P

OUT_ROOT = os.environ.get('OUT_ROOT', 'Z:/太极营')
RESULT = os.path.join(ROOT, '_lel', 'api', 'todo_live.json')


def main():
    cookie = os.environ.get('XQD_COOKIE', '').strip()
    plat = P.QianliaoPlatform(cookie=cookie) if cookie else None
    if plat is None:
        print('!! 缺少 XQD_COOKIE')
        return 1

    camps = []
    for kind in ('正式营', '体验营'):
        try:
            lst = plat.list_camps(kind)
            print('%s: %d 个营' % (kind, len(lst)))
            camps.extend(lst)
        except Exception as e:
            print('  %s 拉取失败: %s' % (kind, e))

    checker = xqd_dedupe.ExistingChecker(OUT_ROOT)
    out = {}
    tot = {'ok': 0, 'missing': 0, 'broken': 0}
    t0 = time.time()

    for camp in camps:
        try:
            les = plat.camp_catalog(camp)
        except Exception as e:
            print('  %s 课表拉取失败: %s' % (camp.name, e))
            continue
        folder = os.path.join(OUT_ROOT, P.safe_name(camp.name))
        alt = xqd_dedupe.legacy_camp_folders(OUT_ROOT, camp.name, len(les))
        rows = []
        c = {'ok': 0, 'missing': 0, 'broken': 0}
        for le in les:
            stem = P.lesson_stem(le)
            st = checker.check_group(folder, stem, le.duration,
                                     alt_folders=alt)
            s = st['status']
            c[s] = c.get(s, 0) + 1
            tot[s] = tot.get(s, 0) + 1
            rows.append({
                'index': le.index, 'title': le.title,
                'duration': le.duration, 'type': le.type,
                'when_date': le.when_date or '',
                'stem': stem, 'status': s,
                'reason': st.get('reason') or '',
                'path': st.get('path') or '',
            })
        out[camp.name] = {'count': len(les), 'rows': rows,
                          'counts': c, 'kind': getattr(camp, 'kind', '')}
        print('  %-28s %3d 节  ok=%-3d missing=%-3d broken=%-3d'
              % (camp.name, len(les), c.get('ok', 0),
                 c.get('missing', 0), c.get('broken', 0)))

    json.dump(out, open(RESULT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print()
    print('合计 %d 节: 已有 %d / 残缺 %d / 缺失 %d   (%.1fs)'
          % (sum(tot.values()), tot['ok'], tot['broken'],
             tot['missing'], time.time() - t0))
    print('结果写入', RESULT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
