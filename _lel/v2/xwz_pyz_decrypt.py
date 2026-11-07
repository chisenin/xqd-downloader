# -*- coding: utf-8 -*-
"""学无止下载器 V2.19.70 —— PYZ 定制加密破解（可复现脚本）

用法：
    # 1) 提取 PyInstaller 归档（需 pyinstxtractor-ng，或用 pyinst_extract.py 自解）
    python -m pyinstxtractor "C:\\LEL\\LEL-Downloader\\LEL-downloader.exe"

    # 2) 批量解密 PYZ 内全部模块
    python decrypt_all.py <PYZ-00.pyz_extracted 目录> <输出目录>

输出：<输出目录> 下是 2638 个可直接反编译的 .pyc
      （1847 个明文 + 791 个带 __pyarmor__ 标记的业务模块）
"""
import os
import sys
import zlib

# ── 密钥派生（还原自 xuewuzhi_runtime/pyimod00_crypto_key.pyc 的反汇编）────────
_seed = 4272740770
_nonce = [23, 123, 35, 2, 251, 195, 5, 32, 171, 118, 113, 41, 31, 101, 168, 23]
_encoded = [3, 231, 101, 222, 225, 130, 253, 174, 37, 181, 102, 116, 220, 58, 177, 239]

CRYPT_BLOCK_SIZE = 16
STREAM_MASK_LEN = 16
PYC_MAGIC = b'\x42\x0d\x0d\x0a'  # Python 3.7


def _mix_state(state, nonce_item, index):
    state = (state + nonce_item + (index + 1) * 2654435761) & 0xFFFFFFFF
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= state >> 17
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def get_mask():
    """派生 16 字节流密码掩码。"""
    state = _seed
    result = []
    for index, item in enumerate(_encoded):
        state = _mix_state(state, _nonce[index & 15], index)
        mask = ((state >> ((index & 3) * 8)) & 255) ^ ((index * 37 + 93) & 255)
        result.append(item ^ mask)
    return bytes(result)


# ── PYZ 流密码 ────────────────────────────────────────────────────────────────
def stream_crypt(data, mask):
    """把数据按 16 列纵向切分，每列用 mask[列号] 派生的替换表做字节替换。

    对应原码：
        payload = data[CRYPT_BLOCK_SIZE:]
        result  = bytearray(len(payload))
        for offset, table in enumerate(_pyi_stream_tables(mask)):
            result[offset::STREAM_MASK_LEN] = payload[offset::STREAM_MASK_LEN].translate(table)
        return bytes(result)
    """
    payload = data[CRYPT_BLOCK_SIZE:]
    tables = [bytes(v ^ item for v in range(256)) for item in mask]
    result = bytearray(len(payload))
    for offset, table in enumerate(tables):
        result[offset::STREAM_MASK_LEN] = payload[offset::STREAM_MASK_LEN].translate(table)
    return bytes(result)


def decrypt_blob(data):
    """PYZ 条目 → 原始 marshal code object 字节。"""
    return zlib.decompress(stream_crypt(data, get_mask()))


def decrypt_all(src_root, out_root):
    mask = get_mask()
    n_ok = n_fail = 0
    fails = []
    for dirpath, _dirnames, filenames in os.walk(src_root):
        for fn in filenames:
            if not fn.endswith('.encrypted'):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src_root)
            # 源文件形如 Xxx.pyc.encrypted → 输出 Xxx.pyc
            if rel.endswith('.pyc.encrypted'):
                rel = rel[:-len('.encrypted')]
            else:
                rel = rel[:-len('.encrypted')] + '.pyc'
            out = os.path.join(out_root, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            try:
                data = decrypt_blob(open(full, 'rb').read())
                with open(out, 'wb') as f:
                    f.write(PYC_MAGIC)
                    f.write(b'\0' * 12)
                    f.write(data)
                n_ok += 1
            except Exception as e:
                n_fail += 1
                if len(fails) < 15:
                    fails.append((rel, str(e)))
    return n_ok, n_fail, fails


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    print('mask =', get_mask().hex())
    n_ok, n_fail, fails = decrypt_all(sys.argv[1], sys.argv[2])
    print('decrypted ok: %d, failed: %d' % (n_ok, n_fail))
    for r, e in fails:
        print('  FAIL', r, e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
