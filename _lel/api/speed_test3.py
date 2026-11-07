# -*- coding: utf-8 -*-
"""严谨限窗测速：固定 30 秒窗口内累计字节，比较不同并发档位。

用法: python _lel/api/speed_test3.py
"""
import os
import sys
import time
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, '_lel', 'api'))

import xqd_api as API   # noqa: E402

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
STOP = threading.Event()
BYTES = [0]
LOCK = threading.Lock()


def http_get(url, timeout=25):
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


def drain(urls, workers):
    """持续拉取直到 STOP。"""
    def worker():
        it = iter(urls)
        while not STOP.is_set():
            try:
                u = next(it)
            except StopIteration:
                return
            try:
                b = http_get(u).read()
            except Exception:
                continue
            with LOCK:
                BYTES[0] += len(b)
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in ts:
        t.start()
    return ts


def window(urls, workers, seconds=30):
    global BYTES
    BYTES = [0]
    STOP.clear()
    ts = drain(urls, workers)
    t0 = time.time()
    time.sleep(seconds)
    STOP.set()
    time.sleep(1.5)
    dt = time.time() - t0
    for t in ts:
        t.join(timeout=2)
    return BYTES[0], dt


def main():
    camp = '引气归源太极营'
    items = API.camp_catalog(camp)
    print('=== 单节课分片并发档位（30 秒窗口）===')
    it = items[0]
    url = API.resolve(camp, it)
    segs, is_master = collect(url)
    print('第一节 %s  分片=%d master=%s' % (it['title'], len(segs), is_master))
    total_bytes = 0
    for w in (1, 4, 8, 16):
        b, dt = window(segs * 3, w, seconds=30)   # 重复清单以避免提前耗尽
        print('  并发=%-3d : %6.1f MB / %5.1fs = %5.2f MB/s'
              % (w, b / 1048576, dt, b / 1048576 / dt))
        if w == 8:
            total_bytes = b

    print()
    print('=== 多节课并行（每节 4 线程，共 4 节）===')
    urls_all = []
    for k in range(4):
        u = API.resolve(camp, items[k])
        s, _ = collect(u)
        urls_all.append(s * 3)
    b, dt = window([u for s in urls_all for u in s], 16, seconds=30)
    print('  4 节 x 4 线程 : %6.1f MB / %5.1fs = %5.2f MB/s'
          % (b / 1048576, dt, b / 1048576 / dt))


if __name__ == '__main__':
    main()
