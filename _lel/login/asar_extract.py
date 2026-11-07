#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""极简 ASAR 读取器：列出 / 提取 Electron app.asar 内的文件。

ASAR 头部是 Chromium Pickle（实测本文件有 4 个 uint32 前置字段）：
    uint32  = 4                     (header pickle payload size)
    uint32  = header_pickle_size    (整个 string pickle 长度，4 对齐)
    uint32  = json_length + 4
    uint32  = json_length
    char[]  = json header (从 offset 16 开始)
文件区从 8 + header_pickle_size 开始（恰等于 16 + json_length）。
header JSON 中每个文件条目：{"size": N, "offset": "相对文件区起点的十进制字符串"}

用法：
    python asar_extract.py list  <app.asar>
    python asar_extract.py dump  <app.asar> <内部路径> [输出文件]
    python asar_extract.py all   <app.asar> <输出目录>
"""
import json
import os
import struct
import sys


def read_header(path):
    with open(path, 'rb') as f:
        blob = f.read()
    if len(blob) < 16:
        raise ValueError('too small to be an asar')
    a, b, c, d = struct.unpack_from('<4I', blob, 0)
    if d <= 0 or 16 + d > len(blob):
        raise ValueError('bad header: %r' % ((a, b, c, d),))
    header = json.loads(blob[16:16 + d].decode('utf-8'))
    base = 8 + b
    if base < 16 + d:
        raise ValueError('header/base mismatch: %d vs %d' % (base, 16 + d))
    return blob, header, base


def walk(node, prefix=''):
    for name, meta in node.get('files', {}).items():
        p = prefix + '/' + name if prefix else name
        if 'files' in meta:
            for x in walk(meta, p):
                yield x
        else:
            yield p, meta


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    cmd, asar = sys.argv[1], sys.argv[2]
    blob, header, base = read_header(asar)
    entries = dict(walk(header))

    if cmd == 'list':
        for p in sorted(entries):
            print('%10d  %s' % (entries[p]['size'], p))
        return 0

    if cmd == 'dump':
        inner = sys.argv[3].lstrip('/')
        if inner not in entries:
            print('NOT FOUND: %s' % inner, file=sys.stderr)
            return 2
        meta = entries[inner]
        off = base + int(meta.get('offset', 0))
        data = blob[off:off + meta['size']]
        out = sys.argv[4] if len(sys.argv) > 4 else None
        if out:
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, 'wb') as f:
                f.write(data)
            print('wrote %s (%d bytes)' % (out, len(data)))
        else:
            sys.stdout.buffer.write(data)
        return 0

    if cmd == 'all':
        outdir = sys.argv[3]
        for p, meta in entries.items():
            dest = os.path.join(outdir, p.replace('/', os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            off = base + int(meta.get('offset', 0))
            with open(dest, 'wb') as f:
                f.write(blob[off:off + meta['size']])
        print('extracted %d files to %s' % (len(entries), outdir))
        return 0

    print('unknown command: %s' % cmd, file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
