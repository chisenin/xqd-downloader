# -*- coding: utf-8 -*-
"""标准 PyInstaller CArchive / PYZ 提取器（支持 AES-encrypted PYZ）。"""
import os
import struct
import sys
import zlib
import marshal
import importlib.util

MAGIC = b'MEI\x0c\x0b\x0a\x0b\x0e'
PYZ_MAGIC = b'PYZ\x00'


def read_carchive(path):
    data = open(path, 'rb').read()
    # 查找所有 cookie
    cookies = []
    idx = 0
    while True:
        i = data.find(MAGIC, idx)
        if i < 0:
            break
        cookies.append(i)
        idx = i + 1
    print('cookies found at:', cookies)
    pkg_start, toc_off, toc_len = None, None, None
    for c in cookies:
        try:
            magic, pkg_len, toc_off, toc_len_, pyvers, pylib = struct.unpack('!8sIIII64s', data[c:c + 88])
        except Exception:
            continue
        pkg_start = c - pkg_len
        toc_abs = pkg_start + toc_off
        if pkg_start < 0 or toc_abs <= 0 or toc_abs + toc_len_ > len(data):
            print('  cookie@%d rejected (pkg_start=%d toc_abs=%d toc_len=%d)' % (c, pkg_start, toc_abs, toc_len_))
            continue
        pkg_start = c - pkg_len
        toc_off, toc_len = toc_abs, toc_len_
        print('  pkg_start=%d pkg_len=%d toc_abs=%d toc_len=%d pyvers=%d lib=%r'
              % (pkg_start, pkg_len, toc_abs, toc_len_, pyvers, pylib.rstrip(b'\x00')))
    return data, pkg_start, toc_off, toc_len


def parse_toc(data, toc_off, toc_len):
    entries = []
    p = toc_off
    end = toc_off + toc_len
    while p < end:
        (elen,) = struct.unpack('!i', data[p:p + 4])
        if elen <= 0:
            break
        e = data[p:p + elen]
        (dlen, doff, clen, ulen, flag, typ) = struct.unpack('!iIIIBc', e[4:4 + 4 + 4 + 4 + 4 + 1])
        name = e[4 + 4 + 4 + 4 + 4 + 1 + 4:].rstrip(b'\x00').decode('utf-8', 'replace')
        entries.append(dict(name=name, offset=doff, csize=clen, usize=ulen, flag=flag, typ=typ.decode('latin-1')))
        p += elen
    return entries


def extract_all(path, outdir):
    data, pkg_start, toc_off, toc_len = read_carchive(path)
    if pkg_start is None:
        raise SystemExit('no archive')
    entries = parse_toc(data, toc_off, toc_len)
    print('TOC entries:', len(entries))
    os.makedirs(outdir, exist_ok=True)
    manifest = []
    for e in entries:
        name = e['name'].replace('/', '__')
        abs_off = pkg_start + e['offset']
        blob = data[abs_off:abs_off + e['csize']]
        if e['typ'] in ('s', 'z') and e['flag'] == 0 and e['csize'] > 0:
            try:
                blob = zlib.decompress(blob)
            except Exception:
                pass
        dst = os.path.join(outdir, name)
        with open(dst, 'wb') as f:
            f.write(blob)
        manifest.append((e['name'], e['typ'], len(blob)))
    for n, t, s in manifest:
        print('  %-4s %10d  %s' % (t, s, n))
    return entries


def read_pyz(path):
    raw = open(path, 'rb').read()
    assert raw[:4] == PYZ_MAGIC, raw[:8]
    pyc_magic = raw[4:8]
    toc_pos = struct.unpack('!i', raw[8:12])[0]
    print('PYZ pyc_magic=%r toc_pos=%d size=%d' % (pyc_magic, toc_pos, len(raw)))
    toc = marshal.loads(raw[toc_pos:])
    print('PYZ modules:', len(toc))
    return raw, pyc_magic, toc


def try_decrypt_pyz(raw, toc, pyc_magic):
    """尝试用 pyimod00_crypto_key 派生 AES key 解密 PYZ。"""
    from Crypto.Cipher import AES
    # 从归档里找 pyimod00_crypto_key
    return None


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'carchive':
        extract_all(sys.argv[2], sys.argv[3])
    elif cmd == 'pyz':
        raw, magic, toc = read_pyz(sys.argv[2])
        for name, (typ, offset, length) in list(toc.items())[:5]:
            print(name, typ, offset, length)
