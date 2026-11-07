# -*- coding: utf-8 -*-
"""从远端隐藏清单重建 links.json（fileId → url）。"""
import sys, os, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd, xqd_app as A
xqd.connect()
links = {}
st = xqd.cache_state()
for f in st:
    if not (f.startswith('.') and 'hls' in f):
        continue
    txt = xqd.read_manifest(f)
    m = A.URL_RE.search(txt)
    if not m: continue
    ids = xqd.biz_ids(txt)
    if ids:
        links[ids[0]] = {'url': m.group(0), 'ts': time.time(), 'camp': ''}
names = A._load(A.NAMES_FILE, {})
hit = 0
for bid, info in names.items():
    if bid in links:
        links[bid]['camp'] = info.get('camp','')
        hit += 1
A._save(A.LINKS_FILE, links)
print('链接 %d 条，与课名映射命中 %d 条' % (len(links), hit))
# 抽样验活
alive = 0
for bid, l in list(links.items())[:6]:
    ok = A.probe_alive(l['url'])
    alive += 1 if ok else 0
    print('  %s %s' % ('✓' if ok else '✗', (names.get(bid) or {}).get('name', bid)[:30]))
