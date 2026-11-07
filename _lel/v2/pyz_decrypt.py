# -*- coding: utf-8 -*-
"""复现 Xuewuzhi 2.19.x 的 PYZ 定制解密。

还原自冻结的 pyimod02_archive（原始文件名 pyimod02_archive_crypto_bootstrap.py）：

    def _pyi_stream_crypt(data, mask):
        payload = data[CRYPT_BLOCK_SIZE:]          # 跳过 16 字节头
        result = bytearray(len(payload))
        for offset, table in enumerate(_pyi_stream_tables(mask)):
            result[offset::STREAM_MASK_LEN] = payload[offset::STREAM_MASK_LEN].translate(table)
        return bytes(result)

    # _pyi_stream_tables(mask): 每字节一张 256 项替换表 table[v] = v ^ mask[i]
    # Cipher.decrypt(data) = _pyi_stream_crypt(data, self._stream_mask)
    # ZlibArchiveReader.extract: obj = cipher.decrypt(obj); obj = zlib.decompress(obj)
"""
import sys
import zlib

from derive_key import get_mask

CRYPT_BLOCK_SIZE = 16
STREAM_MASK_LEN = 16


def stream_crypt(data, mask):
    payload = data[CRYPT_BLOCK_SIZE:]
    tables = [bytes(v ^ item for v in range(256)) for item in mask]
    result = bytearray(len(payload))
    for offset, table in enumerate(tables):
        result[offset::STREAM_MASK_LEN] = payload[offset::STREAM_MASK_LEN].translate(table)
    return bytes(result)


def decrypt_blob(data):
    return zlib.decompress(stream_crypt(data, get_mask()))


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    try:
        out = decrypt_blob(d)
        print('zlib OK len', len(out), 'head', out[:16].hex())
    except Exception as e:
        print('fail:', e)
        print('stream head', stream_crypt(d, get_mask())[:32].hex())
