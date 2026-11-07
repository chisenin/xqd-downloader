# -*- coding: utf-8 -*-
"""全量扫描 272 节的清单类型 + 建立课表缓存。

只拉清单（每节 1 次 manifest GET），不下分片。
输出 _lel/api/kind_scan.json：
  {营名: [{title, type, when, duration, kind, url?}]}
kind ∈ media / master / drm / direct / fail
"""
import os
import sys
import json
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import xqd_platform as P
import xqd_engine as E

# ★ 凭据不在源码里 —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import xqd_creds            # noqa: E402

COOKIE = xqd_creds.load_cookie()

OUT = os.path.join(ROOT, '_lel', 'api', 'kind_scan.json')


def kind_of(url):
    code, body = E.http_get(url, timeout=30)
    if code != 200:
        return 'http_%s' % code, ''
    if not body.startswith(b'#EXTM3U'):
        return 'direct', ''
    text = body.decode('utf-8', 'replace')
    if 'EXT-X-STREAM-INF' in text:
        return 'master', ''
    if 'EXT-X-KEY' in text:
        return 'drm', text
    return 'media', ''


def main():
    plat = P.QianliaoPlatform(cookie=COOKIE)
    result = {}
    grand = collections.Counter()
    for kind in ('正式营', '体验营'):
        for camp in plat.list_camps(kind):
            try:
                lessons = plat.camp_catalog(camp)
            except Exception as e:
                print('!! %s 课表失败：%s' % (camp.name, e))
                continue
            rows = []
            for i, le in enumerate(lessons):
                try:
                    url = plat.resolve(camp, le)
                    k, _ = kind_of(url)
                except Exception as e:
                    k = 'fail'
                    url = ''
                    print('  !! %s / %s → %s' % (camp.name, le.title, e))
                rows.append({
                    'title': le.title, 'index': le.index,
                    'type': le.type, 'when': le.when,
                    'duration': le.duration,
                    'when_date': le.when_date, 'kind': k,
                })
                grand[k] += 1
            result[camp.name] = {'kind': kind, 'rows': rows}
            print('%-30s %3d 节  %s' % (
                camp.name, len(rows),
                dict(collections.Counter(r['kind'] for r in rows))))
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print('\n总览：%s  共 %d 节' % (dict(grand), sum(grand.values())))
    print('已写入 %s' % OUT)


if __name__ == '__main__':
    main()
