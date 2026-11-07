# -*- coding: utf-8 -*-
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd, xqd_export as E

xqd.connect()
links = E.collect_links()
drm = [(k,v) for k,v in links.items() if 'voddrm' in v]
plain = [(k,v) for k,v in links.items() if 'voddrm' not in v]
print('DRM=%d 明文=%d' % (len(drm), len(plain)))

def dur(t):
    return sum(float(x) for x in re.findall(r'#EXTINF:([\d.]+)', t))

for label, pool in (('DRM', drm[:2]), ('明文', plain[:2])):
    for k, v in pool:
        d, fn, q = E.split_dir_query(v)
        code, body = E.http_get(v, timeout=20)
        print('\n== %s fileId=%s code=%s' % (label, k[:14], code))
        if code != 200:
            print('   (签名可能已失效)'); continue
        t = body.decode('utf-8','replace')
        print('   清单: len=%d EXTINF=%.1fs 段=%d hasKEY=%s' % (len(body), dur(t), t.count('#EXTINF'), 'EXT-X-KEY' in t))
        print('   首5行:', [l[:90] for l in t.splitlines()[:5]])
        # 同目录候选明文
        found = 0
        for n in range(1440275, 1440300):
            cd = 'v.f%d.m3u8' % n
            c2, b2 = E.http_get('%s%s?%s' % (d, cd, E.query_without(q)), timeout=15)
            if c2 == 200 and b2.startswith(b'#EXTM3U'):
                t2 = b2.decode('utf-8','replace')
                print('   孪生 %s: len=%d EXTINF=%.1fs 段=%d hasKEY=%s 匹配时长=%s'
                      % (cd, len(b2), dur(t2), t2.count('#EXTINF'), 'EXT-X-KEY' in t2,
                         abs(dur(t2)-dur(t))<1.0))
                found += 1
        if not found: print('   (同目录无明文孪生)')
