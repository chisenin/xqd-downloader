# -*- coding: utf-8 -*-
"""网易课堂（163）视频加密地址解密内核。

来源：学无止下载器 v1.5.0 的 Source/core.dec（明文 JS），逻辑等价于其
getToken().formatM3u8EncryptUrl()。

原 JS 流程：
    decryptAES(k, v):
        key   = L(v)                       # 由 charListMap/charEnlist 派生的 16 字节
        raw   = base64decode(k)
        iv    = raw[:16]
        body  = raw[16:]
        plain = AES-CBC-PKCS7(key, iv, body)
        return JSON(plain up to first '}')

    formatM3u8EncryptUrl(e):
        r = decryptAES(e.k, e.v)
        return e.videoUrl + "&token=" + r.k

本模块把上述逻辑搬到 Python，可独立使用。
"""
import base64
import json
import re

from Crypto.Cipher import AES

# --- 密钥派生表（来自 core.dec 的 charListMap / charEnlist）---------------
# charEnlist1 = 小写 a-z，charEnlist2 = 大写 A-Z，charEnlist3 = 数字 0-9
_CHAR_ELISTS = {
    1: list('abcdefghijklmnopqrstuvwxyz'),
    2: list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'),
    3: list('0123456789'),
}

# v_<n> -> [(charEnlist 编号, 字符下标), ...]
_CHAR_LIST_MAP = {
    0: [(3, 1), (1, 2), (1, 4), (2, 4), (2, 18), (2, 12), (2, 5), (2, 18),
        (2, 4), (1, 0), (2, 22), (1, 11), (2, 6), (2, 16), (1, 7), (2, 24)],
    1: [(3, 3), (1, 5), (1, 15), (3, 4), (1, 23), (1, 18), (3, 9), (3, 2),
        (3, 2), (1, 14), (1, 20), (1, 22), (3, 5), (1, 16), (3, 7), (3, 2)],
    2: [(2, 16), (2, 7), (1, 7), (2, 24), (1, 17), (2, 4), (1, 4), (2, 18),
        (2, 12), (2, 5), (2, 18), (2, 4), (1, 0), (2, 22), (1, 11), (2, 6)],
    3: [(2, 18), (1, 4), (1, 7), (2, 24), (1, 17), (2, 15), (1, 4), (2, 18),
        (2, 11), (2, 5), (2, 18), (1, 14), (1, 0), (2, 22), (1, 11), (3, 5)],
}


def derive_key(version):
    """按 version 号派生 16 字节 AES 密钥。"""
    v = int(version)
    if v not in _CHAR_LIST_MAP:
        raise ValueError('unknown key version: %r' % (version,))
    return ''.join(_CHAR_ELISTS[t][i] for t, i in _CHAR_LIST_MAP[v]).encode('ascii')


def decrypt_aes(k_b64, version):
    """解出明文 JSON。失败返回 None（与原 JS 行为一致）。"""
    try:
        raw = base64.b64decode(k_b64)
        iv, body = raw[:16], raw[16:]
        if not body:
            return None
        plain = AES.new(derive_key(version), AES.MODE_CBC, iv).decrypt(body)
        pad = plain[-1]
        if 1 <= pad <= 16:
            plain = plain[:-pad]
        text = plain.decode('utf-8', 'replace')
        end = text.find('}')
        if end == -1:
            return None
        return json.loads(text[:end + 1])
    except Exception:
        return None


def format_m3u8_encrypt_url(info):
    """把带 k/v 的视频信息还原为可直连的 m3u8 URL。

    info 需含 videoUrl / k / v。返回 (url, error)；
    无需解密时 error 为 None，直接回传 videoUrl。
    """
    url = info.get('videoUrl')
    k = info.get('k')
    v = info.get('v')
    if not url:
        return None, 'missing videoUrl'
    if not k:
        return url, None
    result = decrypt_aes(k, v)
    if not result:
        return None, 'decryptAES fail'
    token = result.get('k') or result.get('videoDecryptionKey')
    if not token:
        return None, 'no token in decrypted payload'
    sep = '&' if '?' in url else '?'
    return '%s%stoken=%s' % (url, sep, token), None


def _selftest():
    """用 v1.5.0 自带样本回归验证。"""
    import os
    sample = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'assets', 'netease_mooc_sample.json')
    if not os.path.exists(sample):
        return 'sample not found: %s' % sample
    data = json.load(open(sample, encoding='utf-8'))
    ok = 0
    for name, info in data.items():
        url, err = format_m3u8_encrypt_url(info)
        if err:
            print('  [%s] FAIL %s' % (name, err))
            continue
        print('  [%s] OK  %s' % (name, url[:110]))
        ok += 1
    return 'passed %d/%d' % (ok, len(data))


if __name__ == '__main__':
    print(_selftest())
