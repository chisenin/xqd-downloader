# -*- coding: utf-8 -*-
"""用真实目录评估：哪些课已完成、哪些缺失、哪些残缺。

数据源：_lel/api/kind_scan.json（含 duration / when_date）
判定：xqd_dedupe.ExistingChecker.check_group（含历史目录）
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import xqd_dedupe
import xqd_platform as P

OUT_ROOT = os.environ.get('OUT_ROOT', 'Z:/太极营')
SCAN = os.path.join(ROOT, '_lel', 'api', 'kind_scan.json')


def main():
    data = json.load(open(SCAN, encoding='utf-8'))
    checker = xqd_dedupe.ExistingChecker(OUT_ROOT)
    total = ok = miss = broken = 0
    todo = []
    for camp_name, blob in data.items():
        rows = blob['rows']
        cnt = {'ok': 0, 'missing': 0, 'broken': 0}
        for r in rows:
            le = P.Lesson(index=r['index'], title=r['title'],
                          duration=r['duration'], ltype=r['type'],
                          camp=camp_name)
            le.when_date = r.get('when_date') or ''
            stem = P.lesson_stem(le)
            folder = os.path.join(OUT_ROOT, P.safe_name(camp_name))
            alt = xqd_dedupe.legacy_camp_folders(
                OUT_ROOT, camp_name, len(rows))
            st = checker.check_group(folder, stem, r['duration'],
                                     alt_folders=alt)
            s = st['status']
            cnt[s] = cnt.get(s, 0) + 1
            total += 1
            if s == 'ok':
                ok += 1
            elif s == 'broken':
                broken += 1
                todo.append((camp_name, r['title'], 'broken', st.get('reason')))
            else:
                miss += 1
                todo.append((camp_name, r['title'], 'missing', ''))
        print('%-30s %3d 节  完成%3d 残缺%3d 缺失%3d'
              % (camp_name, len(rows), cnt.get('ok', 0),
                 cnt.get('broken', 0), cnt.get('missing', 0)))
    print('\n合计 %d 节：完成 %d，残缺 %d，缺失 %d'
          % (total, ok, broken, miss))
    print('需要下载 %d 节' % len(todo))
    with open(os.path.join(ROOT, '_lel', 'api', 'todo_list.json'),
              'w', encoding='utf-8') as f:
        json.dump([{'camp': c, 'title': t, 'status': s, 'reason': r}
                   for c, t, s, r in todo], f, ensure_ascii=False, indent=1)
    for c, t, s, r in todo[:40]:
        print('  [%s] %s / %s %s' % (s, c, t, r))


if __name__ == '__main__':
    main()
