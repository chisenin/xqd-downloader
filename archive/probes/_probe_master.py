# -*- coding: utf-8 -*-
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd_app as A
names = A._load(A.NAMES_FILE, {})
links = A._load(A.LINKS_FILE, {})
by_title = {}
for bid, info in names.items():
    if info.get('camp') == '引气归源太极营':
        by_title.setdefault(info.get('name'), bid)
for title in ['开营典礼：龟形导引功教学', '五行导引功第一课：龟形导引功教学']:
    bid = by_title.get(title)
    url = links[bid]['url']
    kind, text = A.classify_manifest(url)
    print('\n== %s  kind=%s' % (title, kind))
    if kind == 'master':
        print(text[:800])
        # 取第一个子清单
        d, fn, q = A.split_dir_query(url)
        m = re.search(r'^([^\s#]+\.m3u8)', text, re.M)
        if m:
            sub = d + m.group(1)
            if '?' not in m.group(1):
                sub += '?' + q
            print('子清单 URL:', sub[:140])
            c2, b2 = A.http_get(sub, timeout=20)
            print('子清单 code=%s len=%d' % (c2, len(b2)))
            if c2 == 200:
                t2 = b2.decode('utf-8','replace')
                print('  首6行:', [l[:80] for l in t2.splitlines()[:6]])
                print('  hasKEY=', 'EXT-X-KEY' in t2, ' 时长=%.1f' % A._extinf_total(t2))
