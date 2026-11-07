# -*- coding: utf-8 -*-
"""腾讯云 SimpleAES 密钥派生尝试。

已知：
  license 端点返回 16 字节 K_lic  = b4293fc3516ee2dd1013c9d17119f8f4
  tp_dp_file 缓存两把  K1 = b4293fc3516ee2dd1013c9d17119f8f4
                    K2 = a960330de271352546148a6536bf60f8
  清单 IV      = a7a3803e1da187d9f029bd288453e7f7
  JWT cipheredOverLayIv / encryptedOverLayKey 是长 hex 串

思路（腾讯云 DRM SimpleAES 常见做法）：
  媒体密钥 = f(K_lic, 文件标识, IV)   —— 例如 md5/sha256 拼接后截断
  逐个尝试派生式，与标准 AES-128-CBC 组合，用真明文首块 P1 校验。
"""
import os, glob, hashlib, hmac, itertools, json, re, io
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

WORK = r'D:\.workbuddy\2026-11-06-20-15-25\cache-analysis'
os.chdir(WORK)

K_LIC = bytes.fromhex('b4293fc3516ee2dd1013c9d17119f8f4')
K2 = bytes.fromhex('a960330de271352546148a6536bf60f8')
IV = bytes.fromhex('a7a3803e1da187d9f029bd288453e7f7')
P1 = bytes.fromhex('474011100042f0250001c10000ff01ff0001fc80144812010646466d70656709')

# 从 JWT 取长 hex 字段
tok = io.open('drm_url.txt', encoding='utf-8').read().strip()
mtok = re.search(r'voddrm\.token\.([A-Za-z0-9_~.-]+?)\.video_', tok).group(1)
parts = mtok.split('~')
jwt_payload_b64 = parts[1] if len(parts) > 1 else parts[0].split('.')[1]
import base64
s = jwt_payload_b64 + '=' * (-len(jwt_payload_b64) % 4)
try:
    JWT = json.loads(base64.urlsafe_b64decode(s))
except Exception as e:
    JWT = {}
    print('JWT 解码失败:', e)

print('JWT 字段:')
for k, v in JWT.items():
    sv = str(v)
    print('  %-22s %s' % (k, sv[:70] + ('...' if len(sv) > 70 else '')))


def ts_check(buf, limit=300):
    n = len(buf) // 188
    sync = pid = 0
    for i in range(min(n, limit)):
        p = buf[i * 188:(i + 1) * 188]
        if len(p) < 188:
            break
        if p[0] != 0x47:
            continue
        sync += 1
        pv = ((p[1] & 0x1F) << 8) | p[2]
        if pv in (0, 256, 257, 4096, 8192, 4352):
            pid += 1
    return sync, pid


def aes_ecb_dec(key, block):
    c = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return c.update(block) + c.finalize()


def aes_ecb_enc(key, block):
    c = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return c.update(block) + c.finalize()


def main():
    data = open(os.path.join(WORK, 'dl_drm', '1440285_2_0.ts'), 'rb').read()
    C1 = data[:16]
    biz = '3270835010862014849'
    tencent = '1440285'

    # 候选派生材料
    mats = {
        'K_LIC': K_LIC,
        'K2': K2,
        'IV': IV,
        'bizfileid': biz.encode(),
        'tencentfid': tencent.encode(),
        'biz+tencent': (biz + tencent).encode(),
        'tencent+biz': (tencent + biz).encode(),
        'biz+tencent+IV': (biz + tencent + IV.hex()).encode(),
    }
    for k, v in JWT.items():
        sv = str(v)
        if len(sv) >= 16 and all(c in '0123456789abcdefABCDEF' for c in sv) and len(sv) % 2 == 0:
            mats['jwt.' + k] = bytes.fromhex(sv)
        elif len(sv) >= 16:
            mats['jwt.' + k] = sv.encode()

    # 派生函数
    def derives(base):
        yield 'md5', hashlib.md5(base).digest()
        yield 'sha256', hashlib.sha256(base).digest()[:16]
        yield 'sha1', hashlib.sha1(base).digest()[:16]

    cands = {}
    for bn, bv in mats.items():
        for dn, dv in derives(bv):
            cands['%s/%s' % (bn, dn)] = dv
    # 双钥组合
    for (n1, v1) in list(mats.items()):
        for (n2, v2) in list(mats.items()):
            if n1 >= n2:
                continue
            for dn, fn in (('md5', hashlib.md5), ('sha256', hashlib.sha256)):
                cands['%s+%s/%s' % (n1, n2, dn)] = fn(v1 + v2).digest()[:16]
            # HMAC
            cands['hmac(%s,%s)' % (n1, n2)] = hmac.new(v1, v2, hashlib.md5).digest()

    print('\n候选密钥数:', len(cands))

    best = (0, 0, '')
    for name, key in cands.items():
        # 1) CBC + 清单 IV
        try:
            c = Cipher(algorithms.AES(key), modes.CBC(IV)).decryptor()
            d = c.update(data) + c.finalize()
            s, p = ts_check(d)
            if p > best[1]:
                best = (s, p, name + ' CBC/清单IV')
                print('  新最佳 sync=%d pid=%d  %s' % (s, p, best[2]))
        except Exception:
            pass
        # 2) CBC + 代数反解 IV（用 P1）
        try:
            dk1 = aes_ecb_dec(key, C1)
            ivs = bytes(a ^ b for a, b in zip(dk1, P1))
            c = Cipher(algorithms.AES(key), modes.CBC(ivs)).decryptor()
            d = c.update(data) + c.finalize()
            s, p = ts_check(d)
            if p > best[1]:
                best = (s, p, name + ' CBC/反解IV')
                print('  新最佳 sync=%d pid=%d  %s' % (s, p, best[2]))
        except Exception:
            pass
        # 3) ECB
        try:
            c = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
            d = c.update(data) + c.finalize()
            s, p = ts_check(d)
            if p > best[1]:
                best = (s, p, name + ' ECB')
                print('  新最佳 sync=%d pid=%d  %s' % (s, p, best[2]))
        except Exception:
            pass

    print('\n最佳:', best)
    if best[1] > 20:
        print('*** 命中！')
    else:
        print('=> 派生式穷举未命中。')


if __name__ == '__main__':
    main()
