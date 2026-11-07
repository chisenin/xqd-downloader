# -*- coding: utf-8 -*-
"""定向提取课程 API 的调用点（playListOfCourse / getCoursePlayUrl / myCourseList）。

按文档结论（docs/01-已验证事实.md）避免重复探测，
本脚本只回答：请求 URL 怎么拼、body 字段叫什么。
"""
import os
import re
import zlib
import gzip

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webcache')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'course_api_context.txt')


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


def load(fn):
    raw = open(os.path.join(WORK, fn), 'rb').read()
    best = ''
    for blob in blobs_of(raw):
        if len(blob) > len(best):
            best = blob.decode('utf-8', 'replace')
    return best


def main():
    targets = ['5b1d1f81c8e82168_0', 'e8ec390c4a92b34e_0', 'c9f8db14ad04439e_0']
    pats = ['playListOfCourse', 'getCoursePlayUrl', 'myCourseList',
            'getSimpleCampDetail', 'transferData', 'onlyCourseCatalogue',
            'courseCatalogue', 'topicId']
    buf = []
    seen_ctx = set()
    for fn in targets:
        fp = os.path.join(WORK, fn)
        if not os.path.exists(fp):
            continue
        t = load(fn)
        buf.append('\n\n############ FILE %s (%d bytes) ############' % (fn, len(t)))
        for p in pats:
            for m in re.finditer(re.escape(p), t):
                i = m.start()
                frag = t[max(0, i - 500):i + 700].replace('\n', ' ')
                key = (p, frag[:80])
                if key in seen_ctx:
                    continue
                seen_ctx.add(key)
                buf.append('\n--- %s @%d ---\n%s' % (p, i, frag))
                if len(seen_ctx) > 60:
                    break

    out = '\n'.join(buf)
    open(OUT, 'w', encoding='utf-8').write(out)
    print('wrote %s (%d bytes)' % (OUT, len(out)))
    print(out[:12000])


if __name__ == '__main__':
    main()
