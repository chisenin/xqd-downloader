# -*- coding: utf-8 -*-
"""探测 CDN 响应头 / DRM token JWT 里是否带课程名（免去 UI 自动化的课名采集）"""
import sys, os, re, json, base64, ssl, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep2 as S

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=ctx))


def head(url, n=6):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        r = op.open(req, timeout=20)
        return r.status, dict(r.headers), r.read(400)
    except Exception as e:
        return None, {'err': str(e)}, b''


S.connect()
st = S._cache_state()
names = [f for f in st if f.startswith('.') and 'hls' in f]
print('清单数:', len(names))

# 取几个样本
samples = []
for f in names:
    txt = S._read_remote_manifest(f)
    u = re.search(r'https?://[^\s"\']+', txt)
    if u:
        samples.append((f, u.group(0)))
    if len(samples) >= 6:
        break

for f, url in samples:
    print('\n===== %s' % f)
    print('URL:', url[:150])
    # 1) DRM token 的 JWT
    m = re.search(r'voddrm\.token\.([A-Za-z0-9_\-]+)~', url)
    if m:
        jwt = m.group(1)
        parts = jwt.split('.')
        print('JWT 段数:', len(parts))
        for i, p in enumerate(parts):
            try:
                pad = '=' * (-len(p) % 4)
                raw = base64.urlsafe_b64decode(p + pad)
                txt2 = raw.decode('utf-8', 'replace')
                if len(txt2) < 1200:
                    print('  JWT[%d]: %s' % (i, txt2[:1000]))
                else:
                    print('  JWT[%d] len=%d (前200) %s' % (i, len(txt2), txt2[:200]))
            except Exception as e:
                print('  JWT[%d] 解码失败 %s' % (i, e))
    # 2) 请求头
    code, hdrs, body = head(url)
    print('HTTP', code)
    for k, v in hdrs.items():
        if k.lower() in ('content-disposition', 'x-cos-meta-name', 'x-video-meta-name',
                         'x-cos-meta-title', 'content-type'):
            print('  ★ %s: %s' % (k, v))
    print('  body 前120:', body[:120])
