# -*- coding: utf-8 -*-
import sys, os, re, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd, xqd_export as E

xqd.connect()
links = E.collect_links()
print('清单链接数:', len(links))
drm = [(k,v) for k,v in links.items() if 'voddrm' in v]
plain = [(k,v) for k,v in links.items() if 'voddrm' not in v]
print('DRM:', len(drm), ' 明文:', len(plain))

def derive_twin(filename):
    m = re.search(r'video_(\d+)_0\.m3u8$', filename)
    if m: return 'v.f%s.m3u8' % m.group(1)
    return None

for k,v in list(plain[:2]) + list(drm[:3]):
    d, fn, q = E.split_dir_query(v)
    tw = derive_twin(fn)
    print('\nfileId=%s  file=%s' % (k[:16], fn[:60]))
    print('  目录:', d)
    print('  派生明文孪生:', tw)
    if tw:
        cand = '%s%s?%s' % (d, tw, E.query_without(q))
        code, body = E.http_get(cand, timeout=20)
        ok = code==200 and body.startswith(b'#EXTM3U')
        haskey = b'EXT-X-KEY' in body
        print('  孪生请求: code=%s ok=%s hasKEY=%s len=%d' % (code, ok, haskey, len(body)))
        if ok:
            txt = body.decode('utf-8','replace')
            print('  首行后:', [l for l in txt.splitlines() if not l.startswith('#')][:2])
