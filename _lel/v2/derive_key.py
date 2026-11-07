# -*- coding: utf-8 -*-
"""复现 Xuewuzhi 客户端 pyimod00_crypto_key 的自定义密钥派生，并解密 PYZ 模块。"""
import os
import struct
import sys
import zlib

M32 = 0xFFFFFFFF

_seed = 4272740770
_nonce = [23, 123, 35, 2, 251, 195, 5, 32, 171, 118, 113, 41, 31, 101, 168, 23]
_encoded = [3, 231, 101, 222, 225, 130, 253, 174, 37, 181, 102, 116, 220, 58, 177, 239]


def _mix_state(state, nonce_item, index):
    state = (state + nonce_item + (index + 1) * 2654435761) & M32
    state ^= (state << 13) & M32
    state ^= state >> 17
    state ^= (state << 5) & M32
    return state & M32


def get_mask():
    state = _seed
    result = []
    for index, item in enumerate(_encoded):
        state = _mix_state(state, _nonce[index & 15], index)
        mask = ((state >> ((index & 3) * 8)) & 255) ^ ((index * 37 + 93) & 255)
        result.append(item ^ mask)
    return bytes(result)


if __name__ == '__main__':
    print('derived key:', get_mask().hex(), repr(get_mask()))
