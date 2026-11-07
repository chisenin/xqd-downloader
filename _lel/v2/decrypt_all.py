# -*- coding: utf-8 -*-
"""批量解密 Xuewuzhi PYZ 内的全部模块，输出可直接反编译的 .pyc。"""
import os
import sys
import zlib

from derive_key import get_mask
from pyz_decrypt import stream_crypt

MASK = get_mask()
PYC_MAGIC = b'\x42\x0d\x0d\x0a'  # Python 3.7


def decrypt_file(path):
    d = open(path, 'rb').read()
    return zlib.decompress(stream_crypt(d, MASK))


def main(src_root, out_root):
    n_ok = n_fail = 0
    fails = []
    for dirpath, dirnames, filenames in os.walk(src_root):
        for fn in filenames:
            if not fn.endswith('.encrypted'):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src_root)
            out = os.path.join(out_root, rel[:-len('.encrypted')] + '.pyc')
            os.makedirs(os.path.dirname(out), exist_ok=True)
            try:
                data = decrypt_file(full)
                with open(out, 'wb') as f:
                    f.write(PYC_MAGIC)
                    f.write(b'\0' * 12)
                    f.write(data)
                n_ok += 1
            except Exception as e:
                n_fail += 1
                if len(fails) < 15:
                    fails.append((rel, str(e)))
    print('decrypted ok: %d, failed: %d' % (n_ok, n_fail))
    for r, e in fails:
        print('  FAIL', r, e)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
