# -*- coding: utf-8 -*-
"""从 webcache 中提取兴趣岛前端的 API 端点、host 与关键字段。

webcache 是 Android WebView 的缓存文件，内容可能是：
  - gzip/deflate 压缩的 JS / HTML
  - 明文 JS
本脚本对每个文件尝试多种解压方式，提取：
  1. 完整 URL（含 host + path）
  2. 以 / 开头的 API 路径
  3. 关键词上下文（transferData / campId / playUrl / voddrm 等）
"""
import os
import re
import zlib
import gzip
import json
import collections
import sys

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webcache')


def blobs_of(b):
    out = [b]
    # gzip
    for m in re.finditer(b'\x1f\x8b\x08', b):
        try:
            out.append(gzip.decompress(b[m.start():]))
        except Exception:
            try:
                out.append(zlib.decompressobj(31).decompress(b[m.start():]))
            except Exception:
                pass
    # raw deflate
    for tag in (b'\x78\x9c', b'\x78\xda', b'\x78\x01'):
        for m in re.finditer(re.escape(tag), b):
            try:
                out.append(zlib.decompress(b[m.start():]))
            except Exception:
                pass
    return out


def main():
    files = sorted(os.listdir(WORK))
    hosts = collections.Counter()
    paths = collections.Counter()
    campids = collections.Counter()
    kw = collections.defaultdict(collections.Counter)
    kw_samples = {}
    js_blobs = []

    for fn in files:
        p = os.path.join(WORK, fn)
        try:
            raw = open(p, 'rb').read()
        except Exception:
            continue
        for blob in blobs_of(raw):
            if len(blob) < 200:
                continue
            t = blob.decode('utf-8', 'replace')
            if 'qianliao' in t or 'transfer' in t or 'campId' in t or 'courseId' in t:
                js_blobs.append((fn, len(t), t))

    print('相关 blob 数: %d' % len(js_blobs))

    for fn, ln, t in js_blobs:
        for m in re.finditer(r'https?://([a-zA-Z0-9.\-]+)(/[A-Za-z0-9/_.{}$\-]{3,100})', t):
            hosts[m.group(1)] += 1
            paths[(m.group(1), m.group(2))] += 1
        # 相对 API 路径（前后有引号）
        for m in re.finditer(r'["\'](/(?:financial/|api/|gate/)[A-Za-z0-9/_.{}$\-]{3,100})["\']', t):
            paths[('REL', m.group(1))] += 1
        for m in re.finditer(r'["\'](/[a-zA-Z0-9\-]+/[a-zA-Z0-9\-]+/[a-zA-Z0-9/_.{}$\-]{3,90})["\']', t):
            paths[('REL', m.group(1))] += 1
        for m in re.finditer(r'\bcampId["\']?\s*[:=]\s*["\']?(\d{6,})', t):
            campids[m.group(1)] += 1

        for k in ('transferData', 'myCourseList', 'playListOfCourse', 'getCoursePlayUrl',
                  'voddrm', 'video_', 'm3u8', 'sign', 'encdomain', 'getSimpleCampDetail',
                  'topicId', 'courseCatalogue', 'onlyCourseCatalogue'):
            n = t.count(k)
            if n:
                kw[k][fn] += n
                if k not in kw_samples:
                    i = t.find(k)
                    kw_samples[k] = (fn, t[max(0, i - 200):i + 300].replace('\n', ' '))

    print('\n=== HOST ===')
    for h, c in hosts.most_common(25):
        print('  %-42s %d' % (h, c))

    print('\n=== PATH (前 60) ===')
    for (h, pp), c in paths.most_common(60):
        print('  %-28s %-72s %d' % (h, pp, c))

    print('\n=== campId (前 30) ===')
    for k, c in campids.most_common(30):
        print('  %-16s %d' % (k, c))

    print('\n=== 关键词命中文件数 ===')
    for k in kw:
        print('  %-24s files=%d  hits=%d' % (k, len(kw[k]), sum(kw[k].values())))

    print('\n=== 关键词上下文样例 ===')
    for k, (fn, ctx) in kw_samples.items():
        print('\n--- %s  [%s] ---' % (k, fn))
        print(ctx[:480])

    # 导出最大的 JS blob 供进一步分析
    if js_blobs:
        js_blobs.sort(key=lambda x: -x[1])
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webcache_big.js')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(js_blobs[0][2])
        print('\n最大 blob -> %s (%d bytes, from %s)' % (out, js_blobs[0][1], js_blobs[0][0]))


if __name__ == '__main__':
    main()
