# -*- coding: utf-8 -*-
"""并发下载测速：看 CDN 能否多连接拉取提速。

用法: python _lel/api/speed_test_par.py [营名] [并发数]
"""
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, '_lel', 'api'))

import xqd_api as API   # noqa: E402

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return OP.open(req, timeout=timeout)


def collect(url):
    body = http_get(url).read().decode('utf-8', 'replace')
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    is_master = any(l.startswith('#EXT-X-STREAM-INF') for l in lines)
    base = url.rsplit('/', 1)[0]
    segs = []
    if is_master:
        for i, l in enumerate(lines):
            if l.startswith('#EXT-X-STREAM-INF') and i + 1 < len(lines):
                segs.append(lines[i + 1] if lines[i + 1].startswith('http')
                            else base + '/' + lines[i + 1])
    else:
        for l in lines:
            if not l.startswith('#'):
                segs.append(l if l.startswith('http') else base + '/' + l)
    return segs, is_master


def run_parallel(segs, workers, limit=20.0):
    total = [0]
    lock = __import__('threading').Lock()
    idx = [0]
    ilock = __import__('threading').Lock()

    def worker():
        while True:
            with ilock:
                if idx[0] >= len(segs):
                    return
                u = segs[idx[0]]
                idx[0] += 1
            try:
                b = http_get(u, timeout=25).read()
            except Exception:
                continue
            with lock:
                total[0] += len(b)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(worker) for _ in range(workers)]
        for f in futs:
            f.result()
    dt = time.time() - t0
    return total[0], dt


def main():
    camp = sys.argv[1] if len(sys.argv) > 1 else '引气归源太极营'
    workers_list = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 \
        else [4, 8, 16]
    items = API.camp_catalog(camp)
    it = items[0]
    url = API.resolve(camp, it)
    segs, is_master = collect(url)
    print('营=%s  分片=%d  master=%s' % (camp, len(segs), is_master))

    for w in workers_list:
        # 只取前 60 片做测试，避免测太久
        sub = segs[:60]
        total, dt = run_parallel(sub, w, limit=20.0)
        print('并发=%-3d : %6.1f MB / %5.1fs = %5.2f MB/s'
              % (w, total / 1048576, dt, total / 1048576 / dt))


if __name__ == '__main__':
    main()
