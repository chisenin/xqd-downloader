# -*- coding: utf-8 -*-
"""定位前端请求封装：baseURL、body 包装（是否 transferData）、拦截器。

前端调用形态已知：
    {url:"/gate/course/playListOfCourse", body:{campId:..., onlyCourseCatalogue:true}}
所以要找出：谁把 url 拼上 baseURL、谁把 body 包成 {transferData:...}。
"""
import os
import re
import zlib
import gzip

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webcache')


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


PATS = ['baseURL', 'transferData', 'axios.create', 'withCredentials',
        'credentials:"include"', "credentials:'include'", 'financial/api',
        'X-Requested-With', 'qianliao.net']


def main():
    for fn in ['5b1d1f81c8e82168_0', 'e8ec390c4a92b34e_0', 'c9f8db14ad04439e_0']:
        fp = os.path.join(WORK, fn)
        if not os.path.exists(fp):
            continue
        t = load(fn)
        print('\n\n############## FILE %s (%d) ##############' % (fn, len(t)))
        for p in PATS:
            idxs = [m.start() for m in re.finditer(re.escape(p), t)]
            if not idxs:
                continue
            print('\n=== %s  x%d ===' % (p, len(idxs)))
            shown = 0
            for i in idxs[:5]:
                frag = t[max(0, i - 400):i + 500].replace('\n', ' ')
                print('  ...%s...' % frag)
                shown += 1
                if shown >= 5:
                    break


if __name__ == '__main__':
    main()
