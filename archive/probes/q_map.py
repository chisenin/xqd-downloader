# -*- coding: utf-8 -*-
"""探索：能否不逐节点击就得到「课名 → fileId」映射。

思路A：清单文件名 md5 是否由某个「课程标识」派生？
        若 md5 = md5(bizFileId) 或 md5(lessonId)，就能反查。
思路B：App 的 SQLite 里是否有 lessonId ↔ fileId ↔ 课名 三者的关联表。
"""
import sys, time, hashlib, re
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()
st = S._cache_state()
mds = {k: v for k, v in st.items() if k.startswith('.') and 'hls' in k}
print('清单文件 %d 个' % len(mds))

# 抽 6 个样本，算 md5 候选
samples = []
for f in list(mds)[:6]:
    txt = S._read_remote_manifest(f)
    ids = S._biz_ids(txt)
    md5name = f.lstrip('.')
    samples.append((f, md5name, ids, txt))
    print('\n%s' % f)
    print('   biz=%s' % ids)
    if ids:
        for cand_name, cand in [
            ('md5(biz)', hashlib.md5(ids[0].encode()).hexdigest()),
            ('md5(biz+appid)', hashlib.md5(('1500020547' + ids[0]).encode()).hexdigest()),
            ('md5(dir)', hashlib.md5(re.search(r'/([0-9a-f]{8}\d{10,})/', txt).group(1).encode()).hexdigest()),
        ]:
            print('   %-16s %s %s' % (cand_name, cand, 'MATCH!' if cand == md5name else ''))
    # 清单正文是否有其它字段（课名？）
    print('   body[0:160]:', txt[:160].replace('\n', ' | '))
