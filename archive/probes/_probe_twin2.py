# -*- coding: utf-8 -*-
"""校验：DRM 课找孪生时是否会串课（同目录多文件）。"""
import sys, os, re, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd_app as A
names = A._load(A.NAMES_FILE, {})
links = A._load(A.LINKS_FILE, {})
rows = []
for bid, info in names.items():
    url = links.get(bid, {}).get('url')
    if not url: continue
    d, fn, q = A.split_dir_query(url)
    rows.append((info.get('name'), bid, d, url))
by_dir = collections.defaultdict(list)
for n,b,d,u in rows: by_dir[d].append(n)
multi = {d:v for d,v in by_dir.items() if len(v)>1}
print('目录数=%d，其中含多课的目录=%d' % (len(by_dir), len(multi)))
for d,v in list(multi.items())[:5]:
    print('  ', d[-30:], '→', v)

# 对每个 DRM 课，找孪生并比对时长
print('\n逐个 DRM 课验证孪生：')
drms = [(n,b,d,u) for n,b,d,u in rows if 'voddrm' in u]
print('DRM 课 %d 节' % len(drms))
ok = mismatch = 0
for n,b,d,u in drms[:8]:
    kind, text = A.classify_manifest(u)
    if kind != 'drm': continue
    want = A._extinf_total(text)
    twins = []
    directory,_,q = A.split_dir_query(u)
    for k in range(1440280, 1440300):
        nm = 'v.f%d.m3u8' % k
        c2,b2 = A.http_get('%s%s?%s' % (directory, nm, A.query_without(q)), timeout=12)
        if c2==200 and b2.startswith(b'#EXTM3U'):
            t2 = b2.decode('utf-8','replace')
            if 'EXT-X-KEY' in t2: continue
            twins.append((nm, A._extinf_total(t2)))
    match = [nm for nm,dur in twins if abs(dur-want) < max(1.0, want*0.005)]
    print('  %-34s DRM=%.1fs  目录内明文候选=%s  → 命中=%s'
          % (n[:32], want, [('%s:%.0fs'%x) for x in twins][:3], match[:1]))
    if match: ok += 1
    else: mismatch += 1
print('\n命中 %d / 未命中 %d' % (ok, mismatch))
