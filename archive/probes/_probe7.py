# -*- coding: utf-8 -*-
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd, xqd_export as E
xqd.connect()
links = E.collect_links()
import collections
pats = collections.Counter()
samples = {}
for k,v in links.items():
    d, fn, q = E.split_dir_query(v)
    # 去掉 token 前缀
    short = re.sub(r'^voddrm\.token\.[^.]*?\.', 'voddrm.token.<JWT>.', fn)
    short = re.sub(r'\?.*$','',short)
    pats[short] += 1
    samples.setdefault(short, v)
for p, c in pats.most_common(20):
    print('%4d  %s' % (c, p[:120]))
