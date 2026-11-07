# -*- coding: utf-8 -*-
"""验证：清单文件名 md5 与业务 fileId / 课名之间是否存在可推导关系。

思路：App 为每节课写一个稳定文件 .<md5>.hls。若 md5 = f(业务fileId)，
则只要有 fileId 就能反推文件名；反之若 md5 与课名相关，也能建立映射。
"""
import sys, os, re, hashlib, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

xqd.connect()
st = xqd.cache_state()
files = [f for f in st if f.startswith('.') and 'hls' in f]
print('清单文件 %d 个' % len(files))

# 每个文件的 (md5, bizfileIds)
rows = []
for f in files:
    txt = xqd.read_manifest(f)
    ids = xqd.biz_ids(txt)
    md5 = f.lstrip('.').split('.')[0]
    rows.append((md5, tuple(ids), st[f][0]))

# 1) md5 是否 = md5(fileId) 的某种形式
print('\n--- 检验 md5(fileId) ---')
hit = 0
for md5, ids, mt in rows:
    for bid in ids:
        for cand, tag in [
            (hashlib.md5(bid.encode()).hexdigest(), 'md5(id)'),
            (hashlib.md5(bid.encode()).hexdigest()[:32], 'md5(id)'),
        ]:
            if cand == md5:
                hit += 1
print('命中:', hit, '/', len(rows))

# 2) 目录段 <8hex><bizfileId> 中的 8hex 与 md5 的关系
print('\n--- 检验 目录 8hex ---')
for f in files[:4]:
    txt = xqd.read_manifest(f)
    u = re.search(r'https?://[^\s"\']+', txt)
    if not u:
        continue
    md5 = f.lstrip('.').split('.')[0]
    m = re.search(r'/([0-9a-f]{8})(\d{15,25})/', u.group(0))
    print('  file=%s' % f)
    print('    md5=%s' % md5)
    if m:
        h, bid = m.group(1), m.group(2)
        print('    8hex=%s  biz=%s' % (h, bid))
        for cand, tag in [
            (hashlib.md5(bid.encode()).hexdigest()[:8], 'md5(biz)[:8]'),
            (hashlib.md5(h.encode()).hexdigest()[:8], 'md5(8hex)[:8]'),
        ]:
            print('      %-16s %s %s' % (tag, cand, 'MATCH' if cand == h else ''))

# 3) 同一 md5 是否对应多个 bizfileId（多码率 master）
m2m = collections.defaultdict(set)
for md5, ids, mt in rows:
    m2m[md5].update(ids)
multi = {k: v for k, v in m2m.items() if len(v) > 1}
print('\n--- md5 → bizIds 映射 ---')
print('不同 md5 数:', len(m2m), ' 其中含多个 bizId 的:', len(multi))

# 4) 统计每个 md5 对应的 bizId 数量分布
cnt = collections.Counter(len(v) for v in m2m.values())
print('bizId 数分布:', dict(cnt))

# 5) 每个 md5 的内容差异 —— 同一课的主清单 vs master
sample = [k for k,v in m2m.items() if len(v)>=1][:3]
for md5 in sample:
    print('\n=== md5 %s ===' % md5)
    for f in files:
        if f.lstrip('.').split('.')[0] == md5:
            txt = xqd.read_manifest(f)
            ids = xqd.biz_ids(txt)
            print('   %-42s ids=%s len=%d' % (f, ids, len(txt)))
            u = re.search(r'https?://[^\s"\']+', txt)
            if u:
                print('      %s' % u.group(0)[:130])
