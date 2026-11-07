# -*- coding: utf-8 -*-
"""解 DRM token（~ 分隔）的 payload，看是否含课名/fileId"""
import sys, os, re, base64, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep2 as S

S.connect()
st = S._cache_state()
names = [f for f in st if f.startswith('.') and 'hls' in f]

seen = set()
for f in names:
    txt = S._read_remote_manifest(f)
    u = re.search(r'https?://[^\s"\']+', txt)
    if not u:
        continue
    url = u.group(0)
    m = re.search(r'voddrm\.token\.(.+?)~', url)
    if not m:
        continue
    blob = m.group(1)
    parts = blob.split('~')
    if len(parts) < 2:
        continue
    for i, p in enumerate(parts):
        try:
            pad = '=' * (-len(p) % 4)
            raw = base64.urlsafe_b64decode(p + pad)
            s = raw.decode('utf-8', 'replace')
            print('--- seg%d (len=%d) ---' % (i, len(s)))
            print(s[:1500])
            print()
        except Exception as e:
            print('  seg%d 解码失败: %s' % (i, e))
    seen.add(blob)
    if len(seen) >= 2:
        break

if not seen:
    print('没有 DRM token 样本')
