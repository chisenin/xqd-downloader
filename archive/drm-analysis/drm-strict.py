# -*- coding: utf-8 -*-
"""DRM 密钥严格校验：不再依赖 188 对齐启发式，改为解析 TS 包头做结构校验。"""
import os, re, io, sys, itertools, hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

WORK = r'D:\.workbuddy\2026-11-06-20-15-25\cache-analysis'
ENC = os.path.join(WORK, 'dl_drm', '1440285_2_0.ts')
KEYS = {
    'k1': bytes.fromhex('24d903141fd8e50a123a6d2133fddfb9'),
    'k2': bytes.fromhex('a960330de271352546148a6536bf60f8'),
    'k3': bytes.fromhex('b4293fc3516ee2dd1013c9d17119f8f4'),
}
IV_M = bytes.fromhex('a7a3803e1da187d9f029bd288453e7f7')

data = open(ENC, 'rb').read()
print('cipher len =', len(data), ' head =', data[:16].hex())


def ts_score(buf):
    """严格校验：按 188 字节切包，检查同步字节 0x47 与包头 PID 自洽。"""
    n = len(buf) // 188
    if n < 10:
        return -1, 0
    good = 0
    pid_ok = 0
    for i in range(min(n, 400)):
        p = buf[i * 188:(i + 1) * 188]
        if len(p) < 188:
            break
        if p[0] != 0x47:
            continue
        good += 1
        pid = ((p[1] & 0x1F) << 8) | p[2]
        if pid in (0, 256, 257, 4096, 8192):
            pid_ok += 1
    return good, pid_ok


def variants(key, iv):
    """产出 (标签, 变换函数) 组合。"""
    out = []

    def cbc(padding):
        def f(b):
            c = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            return c.update(b) + c.finalize()
        return f

    def ecb():
        def f(b):
            c = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
            return c.update(b) + c.finalize()
        return f

    def ctr(ivx):
        def f(b):
            c = Cipher(algorithms.AES(key), modes.CTR(ivx)).decryptor()
            return c.update(b) + c.finalize()
        return f

    def cfb(ivx):
        def f(b):
            c = Cipher(algorithms.AES(key), modes.CFB(ivx)).decryptor()
            return c.update(b) + c.finalize()
        return f

    def ofb(ivx):
        def f(b):
            c = Cipher(algorithms.AES(key), modes.OFB(ivx)).decryptor()
            return c.update(b) + c.finalize()
        return f

    out.append(('CBC', cbc(None)))
    out.append(('CBC-skip16', lambda b: cbc(None)(b[16:])))
    out.append(('ECB', ecb()))
    out.append(('CTR', ctr(iv)))
    out.append(('CFB', cfb(iv)))
    out.append(('OFB', ofb(iv)))
    # 逐块 (每 16 字节) 重置 IV
    def cbc_perblock(b):
        res = bytearray()
        for p in range(0, len(b) - 15, 16):
            c = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            res += c.update(b[p:p + 16])
        return bytes(res)
    out.append(('CBC-per16', cbc_perblock))
    # 逐 TS 包重置 IV（188 不是 16 倍数，用 ECB 不行；改用 CBC 逐 16 块+IV 派生）
    # IV = 清单IV XOR 段序号
    for si in (1, 2, 3):
        ivx = bytes(a ^ b for a, b in zip(iv, si.to_bytes(16, 'big')))
        out.append(('CTR-iv^%d' % si, ctr(ivx)))
        out.append(('CBC-iv^%d' % si, cbc(None)))
    return out


def key_variants(k):
    yield ('raw', k)
    yield ('rev', k[::-1])
    yield ('wordrev', b''.join(k[i:i + 4][::-1] for i in range(0, 16, 4)))
    yield ('nibble', bytes(((b >> 4) | ((b & 0xF) << 4)) for b in k))
    yield ('sha256', hashlib.sha256(k).digest()[:16])
    yield ('md5', hashlib.md5(k).digest())


print('\n=== 严格判据穷举 ===')
best = []
for kn, k0 in KEYS.items():
    for kname, k in key_variants(k0):
        for label, fn in variants(k, IV_M):
            try:
                d = fn(data)
            except Exception:
                continue
            g, p = ts_score(d)
            if g > 0 or p > 0:
                best.append((g, p, kn, kname, label))
            # 也试零 IV
            if label in ('CBC', 'CTR'):
                try:
                    if label == 'CBC':
                        c = Cipher(algorithms.AES(k), modes.CBC(bytes(16))).decryptor()
                    else:
                        c = Cipher(algorithms.AES(k), modes.CTR(bytes(16))).decryptor()
                    d2 = c.update(data) + c.finalize()
                    g2, p2 = ts_score(d2)
                    if g2 > 0 or p2 > 0:
                        best.append((g2, p2, kn, kname, label + '-iv0'))
                except Exception:
                    pass

best.sort(reverse=True)
if best:
    print('有命中 (top 15):')
    for b in best[:15]:
        print('  sync=%d pidok=%d  %s %s %s' % b)
else:
    print('全部 0命中：这些密钥/IV/模式组合都解不出合法 TS。')

# 反向诊断：找明文 TS 头特征在密文中的位置
print('\n=== 密文统计诊断 ===')
print('0x47 出现次数:', data.count(b'\x47'), '/', len(data), '= %.5f' % (data.count(b'\x47') / len(data)))
print('前16字节熵样本:', data[:32].hex())
