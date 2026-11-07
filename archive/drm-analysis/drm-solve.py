# -*- coding: utf-8 -*-
"""用真实明文首块代数反解 IV，验证腾讯云 SimpleAES。

明文基准（短课明文分片 b01d54a4.../0.ts 头部，188 对齐 831/831 全中）：
  P1 = 474011100042f0250001c10000ff01ff0001fc80144812010646466d70656709
若为 AES-128-CBC：  IV = D_K(C1) XOR P1
再用解出的 IV 解密全文件，检验 188 对齐。
若为 AES-128-CFB128：IV = D_K(C1) XOR P1（同式）
若为 AES-128-ECB：直接检验
若为 AES-128-CTR：P1 = C1 XOR E_K(IV)  -> 穷举常见 IV
"""
import os, glob, hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

WORK = r'D:\.workbuddy\2026-11-06-20-15-25\cache-analysis'
os.chdir(WORK)

KEYS = {
    'license_b429': 'b4293fc3516ee2dd1013c9d17119f8f4',
    'license_a960': 'a960330de271352546148a6536bf60f8',
    'dp_24d903': '24d903141fd8e50a123a6d2133fddfb9',
    'dp_a0c972': 'a0c9723787fa21920cba6b7417e855a9',
    'dp_9569c4': '9569c413a078ebfeaa86ac9898767adf',
}
# 真明文首块（来自短课明文分片）
P1 = bytes.fromhex('474011100042f0250001c10000ff01ff0001fc80144812010646466d70656709')
MANIFEST_IV = bytes.fromhex('a7a3803e1da187d9f029bd288453e7f7')


def aes_ecb(key, block):
    c = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return c.update(block) + c.finalize()


def ts_check(buf, limit=500):
    n = len(buf) // 188
    sync = pid = pusi = 0
    for i in range(min(n, limit)):
        p = buf[i * 188:(i + 1) * 188]
        if len(p) < 188:
            break
        if p[0] != 0x47:
            continue
        sync += 1
        pidv = ((p[1] & 0x1F) << 8) | p[2]
        if pidv in (0, 256, 257, 4096, 8192, 4352):
            pid += 1
        if p[1] & 0x40:
            pusi += 1
    return sync, pid, pusi


def try_cbc(key, iv, data, label):
    try:
        c = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        d = c.update(data) + c.finalize()
    except Exception:
        return None
    return ts_check(d)


def main():
    data = open(os.path.join(WORK, 'dl_drm', '1440285_2_0.ts'), 'rb').read()
    C1 = data[:16]
    print('密文首块 C1 =', C1.hex())
    print('已知明文 P1 =', P1.hex())
    print('清单 IV     =', MANIFEST_IV.hex())
    print()

    best = (0, 0, 0, '')
    for kn, khex in KEYS.items():
        key = bytes.fromhex(khex)
        dk1 = aes_ecb(key, C1)
        iv_solved = bytes(a ^ b for a, b in zip(dk1, P1))
        print('=== 密钥 %s' % kn)
        print('    D_K(C1)      =', dk1.hex())
        print('    反解 IV(CBC) =', iv_solved.hex())
        # 1) CBC + 反解 IV
        for name, iv in (('反解IV', iv_solved), ('清单IV', MANIFEST_IV), ('零IV', bytes(16))):
            r = try_cbc(key, iv, data, name)
            if r:
                s, p, u = r
                print('      CBC/%-8s sync=%d pid=%d pusi=%d' % (name, s, p, u))
                if p > best[1]:
                    best = (s, p, u, '%s CBC/%s' % (kn, name))
        # 2) CFB128 + 反解 IV
        from cryptography.hazmat.decrepit.ciphers import modes as dm
        for name, iv in (('反解IV', iv_solved), ('清单IV', MANIFEST_IV)):
            try:
                c = Cipher(algorithms.AES(key), dm.CFB(iv)).decryptor()
                d = c.update(data) + c.finalize()
                s, p, u = ts_check(d)
                print('      CFB/%-8s sync=%d pid=%d pusi=%d' % (name, s, p, u))
                if p > best[1]:
                    best = (s, p, u, '%s CFB/%s' % (kn, name))
            except Exception:
                pass
        # 3) ECB
        c = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
        d = c.update(data) + c.finalize()
        s, p, u = ts_check(d)
        print('      ECB          sync=%d pid=%d pusi=%d' % (s, p, u))
        if p > best[1]:
            best = (s, p, u, '%s ECB' % kn)
        # 4) CTR 常用 IV
        for ivname, ivx in (('zero', bytes(16)), ('清单IV', MANIFEST_IV),
                            ('md5(清单IV)', hashlib.md5(MANIFEST_IV).digest())):
            c = Cipher(algorithms.AES(key), modes.CTR(ivx)).decryptor()
            d = c.update(data) + c.finalize()
            s, p, u = ts_check(d)
            if s > 3 or p > 1:
                print('      CTR/%-9s sync=%d pid=%d pusi=%d' % (ivname, s, p, u))
            if p > best[1]:
                best = (s, p, u, '%s CTR/%s' % (kn, ivname))
        print()

    print('最佳:', best)
    if best[1] > 20:
        print('*** 命中！DRM 解密方案成立')
    else:
        print('=> 仍未命中。')

    # 关键验证：反解 IV 是否恰好等于清单 IV？（若相等则说明 key 对，只是我判据有误）
    print('\n=== 关键交叉验证 ===')
    for kn, khex in KEYS.items():
        key = bytes.fromhex(khex)
        dk1 = aes_ecb(key, C1)
        iv_s = bytes(a ^ b for a, b in zip(dk1, P1))
        print('  %-14s 反解IV == 清单IV ? %s' % (kn, iv_s == MANIFEST_IV))


if __name__ == '__main__':
    main()
