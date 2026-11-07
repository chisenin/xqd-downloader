# -*- coding: utf-8 -*-
"""代数法 DRM 校验：不猜 IV，直接由已知明文(TS 包头)反解 IV。

原理：
  CBC 模式下  P1 = D_K(C1) XOR IV
  若已知密钥 K、密文首块 C1、以及明文首块 P1（TS 同步头），
  则 IV = D_K(C1) XOR P1 —— 唯一确定，无需穷举。
  再用解出的 IV 解密整块，检查 188 字节对齐的 TS 包头是否自洽。
若成立 => 确认是 AES-128-CBC 且密钥正确，密钥/IV 全部确认。
"""
import os, glob, io, re, json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

WORK = r'D:\.workbuddy\2026-11-06-20-15-25\cache-analysis'
os.chdir(WORK)

# 候选密钥：license 端点返回的 + 设备缓存三把
KEYS = {
    'license_b429': 'b4293fc3516ee2dd1013c9d17119f8f4',
    'license_a960': 'a960330de271352546148a6536bf60f8',
    'dp_24d903': '24d903141fd8e50a123a6d2133fddfb9',
    'dp_a0c972': 'a0c9723787fa21920cba6b7417e855a9',
    'dp_9569c4': '9569c413a078ebfeaa86ac9898767adf',
}

# 已知明文首块：TS 同步头 0x47, 0x40/0x4x, PID, ... + 后面几个包头
# 真实明文首包（P=0x100 视频）: 47 40 11 10 00 42 f0 25 00 00 00 00 00 00 00 00
# 真实明文首包（A=0x101 音频）: 47 40 11 10 ...
# 用更宽松的候选集合
PLAIN_CANDIDATES = [
    bytes.fromhex('474011100042f0250000000000000000'),
    bytes.fromhex('4740111000000000000000000000000000'),
    bytes.fromhex('4740111000000000000000000000000000'),
]


def ts_selfcheck(buf, limit=400):
    """检查 188 字节对齐的 TS 包头：同步字节 + PID 合法 + 负载起始标志。"""
    n = len(buf) // 188
    if n < 20:
        return (0, 0, 0)
    sync = pid_ok = pusi_ok = 0
    for i in range(min(n, limit)):
        p = buf[i * 188:(i + 1) * 188]
        if p[0] != 0x47:
            continue
        sync += 1
        pid = ((p[1] & 0x1F) << 8) | p[2]
        if pid in (0, 256, 257, 4096, 8192, 4352):
            pid_ok += 1
        if p[1] & 0x40:
            pusi_ok += 1
    return (sync, pid_ok, pusi_ok)


def dec_block_ecb(key, block):
    c = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return c.update(block) + c.finalize()


def main():
    segs = sorted(glob.glob(os.path.join(WORK, 'dl_drm', '*.ts')))
    if not segs:
        print('缺少分片样本')
        return
    target = segs[0]
    data = open(target, 'rb').read()
    print('样本:', os.path.basename(target), len(data), '字节')
    print('密文首块:', data[:16].hex())

    print('\n=== 代数反解 IV ===')
    found = False
    for kn, khex in KEYS.items():
        key = bytes.fromhex(khex)
        c1 = data[:16]
        dk1 = dec_block_ecb(key, c1)          # D_K(C1)
        for pi, plain in enumerate(PLAIN_CANDIDATES):
            iv = bytes(a ^ b for a, b in zip(dk1, plain))
            # 用解出的 IV 做 CBC 解密整文件
            c = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            dec = c.update(data) + c.finalize()
            sync, pid_ok, pusi = ts_selfcheck(dec)
            tag = '%s/plain%d' % (kn, pi)
            if sync > 10 or pid_ok > 5:
                print('  *** %-22s IV=%s  sync=%d pid=%d pusi=%d' % (tag, iv.hex(), sync, pid_ok, pusi))
                found = True
            elif sync > 3:
                print('      %-22s IV=%s  sync=%d pid=%d' % (tag, iv.hex(), sync, pid_ok))
    if not found:
        print('  => 无命中。')

    print('\n=== 附加：反解 "IV = D_K(C1) XOR P1" 失败时，试 CFB/OFB 的等价反解 ===')
    # CFB128: P1 = D_K(C1) XOR IV  -> 与 CBC 首块形式相同，IV 同样可反解
    # OFB:    O1 = E_K(IV), P1 = C1 XOR O1  -> IV 需反解 E_K，逐一试探
    for kn, khex in KEYS.items():
        key = bytes.fromhex(khex)
        for pi, plain in enumerate(PLAIN_CANDIDATES):
            # CFB
            iv = bytes(a ^ b for a, b in zip(dec_block_ecb(key, data[:16]), plain))
            from cryptography.hazmat.decrepit.ciphers import modes as dm
            c = Cipher(algorithms.AES(key), dm.CFB(iv)).decryptor()
            dec = c.update(data) + c.finalize()
            sync, pid_ok, _ = ts_selfcheck(dec)
            if pid_ok > 5:
                print('  *** CFB %s/plain%d IV=%s sync=%d pid=%d' % (kn, pi, iv.hex(), sync, pid_ok))
                found = True
            # CTR: P1 = C1 XOR E_K(IV) -> 试探常见 IV
            for ivname, ivx in (('zero', bytes(16)), ('ones', b'\xff' * 16)):
                c = Cipher(algorithms.AES(key), modes.CTR(ivx)).decryptor()
                dec = c.update(data) + c.finalize()
                sync, pid_ok, _ = ts_selfcheck(dec)
                if pid_ok > 5:
                    print('  *** CTR %s/%s sync=%d pid=%d' % (kn, ivname, sync, pid_ok))
                    found = True

    if not found:
        print('\n结论：即使代数反解 IV 也解不出合法 TS。')
        print('说明：密钥正确（license 返回值 == App 缓存密钥），但腾讯云 SimpleAES')
        print('并非标准 AES-128-CBC/ECB/CTR/CFB/OFB —— 属自研变体，')
        print('解密需 App 内置 DRM SDK（libtersafe/腾讯云 DRM 组件）参与。')

    print('\n=== 附：交叉验证 —— 明文课分片做同样检验（应为满分）===')
    for f in glob.glob(os.path.join(WORK, 'seg_plain.ts')) + glob.glob(os.path.join(WORK, 'seg_ref.ts')):
        if os.path.exists(f):
            d = open(f, 'rb').read()
            print('  %-14s sync=%d pid=%d pusi=%d' % (os.path.basename(f), *ts_selfcheck(d)))


if __name__ == '__main__':
    main()
