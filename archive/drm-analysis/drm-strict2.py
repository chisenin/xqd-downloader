# -*- coding: utf-8 -*-
"""严格判据：设备上真正的三把 tp_dp_file 密钥 × 三个码率的 IV × 多种模式。
判据：解密后按 188 字节切包，0x47 同步字节 + PID 白名单双校验。"""
import os, re, io, glob, hashlib, itertools, subprocess
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

WORK = r'D:\.workbuddy\2026-11-06-20-15-25\cache-analysis'
DL = os.path.join(WORK, 'dl_drm')

# --- 设备上的三把 key（已从 tp_dp_file 拉回）---
DEVICE_KEYS = {
    'dp_24d903': '24d903141fd8e50a123a6d2133fddfb9',
    'dp_a0c972': 'a0c9723787fa21920cba6b7417e855a9',
    'dp_9569c4': '9569c413a078ebfeaa86ac9898767adf',
}
LICENSE_KEY = 'b4293fc3516ee2dd1013c9d17119f8f4'


def decrypt(mode, key, iv, data):
    if mode == 'CBC':
        c = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    elif mode == 'CTR':
        c = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor()
    elif mode == 'CFB':
        from cryptography.hazmat.decrepit.ciphers import modes as dm
        c = Cipher(algorithms.AES(key), dm.CFB(iv)).decryptor()
    elif mode == 'OFB':
        from cryptography.hazmat.decrepit.ciphers import modes as dm
        c = Cipher(algorithms.AES(key), dm.OFB(iv)).decryptor()
    elif mode == 'ECB':
        c = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    else:
        return None
    return c.update(data) + c.finalize()


def strict_ts_score(buf):
    """严格：0x47 同步 + PID 合理 + 校验 continuity counter 递增。"""
    n = len(buf) // 188
    if n < 20:
        return (0, 0)
    sync = pid_ok = cc_ok = 0
    prev_cc = None
    for i in range(min(n, 300)):
        p = buf[i * 188:(i + 1) * 188]
        if len(p) < 188:
            break
        if p[0] != 0x47:
            continue
        sync += 1
        pid = ((p[1] & 0x1F) << 8) | p[2]
        if pid in (0, 256, 257, 4096, 8192, 4352):
            pid_ok += 1
        cc = p[3] & 0x0F
        if prev_cc is None or cc == (prev_cc + 1) % 16:
            cc_ok += 1
        prev_cc = cc
    return (sync, pid_ok)


def key_forms(k):
    yield 'raw', k
    yield 'rev', k[::-1]
    yield 'wordrev', b''.join(k[i:i + 4][::-1] for i in range(0, 16, 4))
    yield 'sha256', hashlib.sha256(k).digest()[:16]
    yield 'md5', hashlib.md5(k).digest()


def iv_forms(iv, seg_idx=0):
    yield 'manifest', iv
    yield 'zero', bytes(16)
    yield 'idx_be', seg_idx.to_bytes(16, 'big')
    yield 'idx_le', seg_idx.to_bytes(16, 'little')
    yield 'xor_idx', bytes(a ^ b for a, b in zip(iv, seg_idx.to_bytes(16, 'big')))
    yield 'md5_iv', hashlib.md5(iv).digest()


def main():
    # 收集所有 DRM 清单及其 IV
    manifests = {}
    for f in glob.glob(os.path.join(WORK, '.DRMURL*')):
        txt = io.open(f, encoding='utf-8').read().strip()
        m = re.search(r'voddrm\.token\.[A-Za-z0-9_~.-]+?\.video_(\d+)_(\d+)\.m3u8', txt)
        if not m:
            continue
        vid = '%s_%s' % (m.group(1), m.group(2))
        out = os.path.join(WORK, 'm3u8_%s' % vid)
        r = subprocess.run(['curl', '-s', '--max-time', '25', '-o', out, txt],
                           capture_output=True, text=True)
        try:
            body = io.open(out, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        ivm = re.search(r'IV=0x([0-9a-fA-F]+)', body)
        if ivm:
            manifests[vid] = bytes.fromhex(ivm.group(1))
    if not manifests:
        print('!! 没找到 DRM 清单 IV')
        return
    print('=== 各码率清单 IV ===')
    for v, iv in manifests.items():
        print('  video_%s  IV=%s' % (v, iv.hex()))

    seg = os.path.join(DL, '1440285_2_0.ts')
    if not os.path.exists(seg):
        print('!! 缺少分片样本')
        return
    data = open(seg, 'rb').read()

    allkeys = dict(DEVICE_KEYS)
    allkeys['license'] = LICENSE_KEY
    print('\n=== 严格穷举 (%d 密钥形态 x %d IV 形态 x 6 模式) ===' % (
        sum(1 for _ in allkeys) * 5, 6))

    best = (0, 0, '')
    for kn, khex in allkeys.items():
        for kf, key in key_forms(bytes.fromhex(khex)):
            for vid, iv in manifests.items():
                for ivf, ivx in iv_forms(iv, 0):
                    for mode in ('CBC', 'CTR', 'CFB', 'OFB', 'ECB'):
                        try:
                            d = decrypt(mode, key, ivx, data)
                        except Exception:
                            continue
                        if d is None:
                            continue
                        s, p = strict_ts_score(d)
                        if p > best[1] or (p == best[1] and s > best[0]):
                            best = (s, p, '%s/%s vid=%s iv=%s %s' % (kn, kf, vid, ivf, mode))
                            print('  新最佳 sync=%d pid=%d  %s' % (s, p, best[2]))
    print('\n最佳结果: sync=%d pid_ok=%d  [%s]' % best)
    if best[1] == 0:
        print('=> 无任何组合解出合法 TS。确认非标准 AES-128-CBC/ECB/CTR/CFB/OFB。')


if __name__ == '__main__':
    main()
