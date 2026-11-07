# -*- coding: utf-8 -*-
"""实测：xqd_engine.parse_manifest 对 master 课能否真正拿到分片。

对照 xqd_pdl.manifest_segments（批处理那套，已验证可下）。
只拉清单与子清单，不下分片。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import xqd_platform as P
import xqd_engine as E
import xqd_pdl as PDL

# ★ 凭据不在源码里 —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import xqd_creds            # noqa: E402

COOKIE = xqd_creds.load_cookie()

N = int(os.environ.get('N', '5'))


def main():
    plat = P.QianliaoPlatform(cookie=COOKIE)
    for camp in plat.list_camps('正式营'):
        lessons = plat.camp_catalog(camp)
        picked = []
        for le in lessons:
            try:
                url = plat.resolve(camp, le)
            except Exception:
                continue
            code, body = E.http_get(url, timeout=30)
            if code != 200 or not body.startswith(b'#EXTM3U'):
                continue
            t = body.decode('utf-8', 'replace')
            if 'EXT-X-STREAM-INF' in t:
                picked.append((le, url))
            if len(picked) >= N:
                break
        if not picked:
            continue
        print('==== 营：%s ====' % camp.name)
        for le, url in picked:
            print('-- %s' % le.title)
            print('   master url: %s' % url[:110])
            segs, kind, note, total = E.parse_manifest(url, quality='max')
            print('   engine: kind=%s note=%s 分片数=%s 总时长=%s'
                  % (kind, note, len(segs) if segs else 0, total))
            if segs:
                c, b = E.http_get(segs[0][0], timeout=30)
                print('   engine 首分片 HTTP=%s len=%s' % (c, len(b)))
            segs2, kind2, note2, total2 = PDL.manifest_segments(url)
            print('   pdl   : kind=%s note=%s 分片数=%s 总时长=%s'
                  % (kind2, note2, len(segs2) if segs2 else 0, total2))
            if segs2:
                c2, b2 = PDL.fetch(segs2[0][0], timeout=30)
                print('   pdl   首分片 HTTP=%s len=%s' % (c2, len(b2)))
        break


if __name__ == '__main__':
    main()
