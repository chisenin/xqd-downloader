# -*- coding: utf-8 -*-
"""定位含 API 端点的 JS blob，并打印端点附近的调用上下文。

目标：搞清三件事
  1. 真实 host（m.qianliao.net / app.qianliao.net / 其他）
  2. 请求体结构（transferData 包法、字段名）
  3. getCoursePlayUrl 返回里播放地址字段名（对应 DRM 孪生规则）
"""
import os
import re
import zlib
import gzip

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webcache')
KEYS = ['myCourseList', 'playListOfCourse', 'getCoursePlayUrl', 'getSimpleCampDetail',
        'transferData', 'onlyCourseCatalogue', 'voddrm', 'encdomain', 'video_']


def blobs_of(b):
    out = [b]
    for m in re.finditer(b'\x1f\x8b\x08', b):
        try:
            out.append(gzip.decompress(b[m.start():]))
        except Exception:
            try:
                out.append(zlib.decompressobj(31).decompress(b[m.start():]))
            except Exception:
                pass
    for tag in (b'\x78\x9c', b'\x78\xda', b'\x78\x01'):
        for m in re.finditer(re.escape(tag), b):
            try:
                out.append(zlib.decompress(b[m.start():]))
            except Exception:
                pass
    return out


def main():
    hits = {}
    for fn in sorted(os.listdir(WORK)):
        fp = os.path.join(WORK, fn)
        if not os.path.isfile(fp):
            continue
        try:
            raw = open(fp, 'rb').read()
        except Exception:
            continue
        for blob in blobs_of(raw):
            if len(blob) < 2000:
                continue
            t = blob.decode('utf-8', 'replace')
            score = sum(t.count(k) for k in KEYS)
            if score < 3:
                continue
            cur = hits.get(fn)
            if cur is None or len(t) > cur[0]:
                hits[fn] = (len(t), t)

    # 按命中数排序
    ranked = sorted(hits.items(), key=lambda kv: -sum(kv[1][1].count(k) for k in KEYS))
    print('候选文件: %d' % len(ranked))
    for fn, (ln, t) in ranked[:6]:
        print('  %-40s %8d bytes  score=%d' % (fn, ln, sum(t.count(k) for k in KEYS)))

    if not ranked:
        return

    fn, (ln, t) = ranked[0]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_bundle.js')
    open(out, 'w', encoding='utf-8').write(t)
    print('\n=== 主 bundle -> %s (%s) ===' % (out, fn))

    for k in KEYS:
        idxs = [m.start() for m in re.finditer(re.escape(k), t)]
        if not idxs:
            continue
        print('\n############ %s  (%d 次) ############' % (k, len(idxs)))
        seen = set()
        for i in idxs[:6]:
            frag = t[max(0, i - 320):i + 420].replace('\n', ' ')
            # 同一段附近只打印一次
            key = frag[:60]
            if key in seen:
                continue
            seen.add(key)
            print('  ...%s...' % frag)


if __name__ == '__main__':
    main()
