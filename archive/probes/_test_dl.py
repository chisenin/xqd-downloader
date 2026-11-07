# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd_app as A
names = A._load(A.NAMES_FILE, {})
links = A._load(A.LINKS_FILE, {})
by_title = {}
for bid, info in names.items():
    if info.get('camp') == '引气归源太极营':
        by_title.setdefault(info.get('name'), bid)

title = '先导课：解谜自然之道'
bid = by_title.get(title)
print('目标:', title, '→ fileId', bid)
url = links[bid]['url']
d, fn, q = A.split_dir_query(url)
print('清单类型判定…')
kind, text = A.classify_manifest(url)
print('  kind =', kind, ' 时长 = %.1fs' % A._extinf_total(text))
out = 'D:/user/chisenin/Videos/引气归源太极营/%s.mp4' % A.safe_name(title)
os.makedirs(os.path.dirname(out), exist_ok=True)
t0=time.time()
good, note, pct = A.download(url, out, progress=lambda p: None)
print('下载:', good, note, '用时 %.1fs' % (time.time()-t0))
if good:
    print('  大小 %.1f MB' % (os.path.getsize(out)/1048576.0))
