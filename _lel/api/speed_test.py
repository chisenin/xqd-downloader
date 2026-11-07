# -*- coding: utf-8 -*-
"""测 CDN 下载速度 vs Z 盘写入速度，判断瓶颈。

用法: python _lel/api/speed_test.py [营名]
"""
import os
import sys
import time
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, '_lel', 'api'))

import xqd_api as API   # noqa: E402

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return OP.open(req, timeout=timeout)


def main():
    camp = sys.argv[1] if len(sys.argv) > 1 else '引气归源太极营'
    items = API.camp_catalog(camp)
    print('营: %s  共 %d 节' % (camp, len(items)))

    # 取第一节（通常较短）做测速
    it = items[0]
    url = API.resolve(camp, it)
    print('第一节: %s' % it['title'])
    print('URL  : %s' % url)
    if not url:
        print('解析失败')
        return

    r = http_get(url)
    body = r.read().decode('utf-8', 'replace')
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    is_master = any(l.startswith('#EXT-X-STREAM-INF') for l in lines)
    print('清单: master=%s  行数=%d' % (is_master, len(lines)))

    # 收集分片 URL
    segs = []
    if is_master:
        base = url.rsplit('/', 1)[0]
        for i, l in enumerate(lines):
            if l.startswith('#EXT-X-STREAM-INF') and i + 1 < len(lines):
                segs.append(lines[i + 1] if lines[i + 1].startswith('http')
                            else base + '/' + lines[i + 1])
    else:
        base = url.rsplit('/', 1)[0]
        for l in lines:
            if not l.startswith('#'):
                segs.append(l if l.startswith('http') else base + '/' + l)
    print('分片数: %d' % len(segs))
    if not segs:
        return

    # ---- 下载测速：限时 20 秒累计字节 ----
    LIMIT = 20.0
    total = 0
    t0 = time.time()
    i = 0
    while time.time() - t0 < LIMIT and i < len(segs):
        u = segs[i]
        try:
            b = http_get(u, timeout=20).read()
        except Exception as e:
            print('  分片 %d 失败: %s' % (i, e))
            i += 1
            continue
        total += len(b)
        i += 1
    dt = time.time() - t0
    print('CDN 下载: %.1f MB / %.1fs = %.1f MB/s  (%d 片)'
          % (total / 1048576, dt, total / 1048576 / dt, i))

    # ---- Z 盘写入测速 ----
    zdir = 'Z:/太极营'
    os.makedirs(zdir, exist_ok=True)
    zp = os.path.join(zdir, '_speed.bin')
    data = b'\0' * (8 * 1048576)
    t0 = time.time()
    written = 0
    with open(zp, 'wb') as f:
        for _ in range(6):
            f.write(data)
            f.flush()
            written += len(data)
    dt = time.time() - t0
    print('Z 写入  : %.1f MB / %.1fs = %.1f MB/s'
          % (written / 1048576, dt, written / 1048576 / dt))
    os.remove(zp)


if __name__ == '__main__':
    main()
