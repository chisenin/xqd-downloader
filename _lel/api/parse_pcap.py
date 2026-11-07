# -*- coding: utf-8 -*-
"""解析 cap.pcap，抽取兴趣岛 App 实际发出的 HTTP 请求（URL / Host / Cookie / body）。

pcap 格式：全局头 24 字节，随后每条记录 16 字节头 + 数据。
只做「应用层 HTTP 明文」的提取，不做完整协议栈还原。
"""
import struct
import sys
import os
import re
from collections import OrderedDict

PCAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cap.pcap')

LINKTYPE_NULL = 0
LINKTYPE_ETHERNET = 1
LINKTYPE_RAW = 101
LINKTYPE_LINUX_SLL = 113
LINKTYPE_LINUX_SLL2 = 276


def read_pcap(path):
    b = open(path, 'rb').read()
    magic = b[:4]
    if magic in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4'):
        endian = '<'
    elif magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d'):
        endian = '>'
    else:
        raise ValueError('not pcap: %r' % magic)
    vmaj, vmin, tz, sig, snap, network = struct.unpack(endian + 'HHiIII', b[4:24])
    off = 24
    n = 0
    while off + 16 <= len(b):
        ts, tsu, incl, orig = struct.unpack(endian + 'IIII', b[off:off + 16])
        off += 16
        data = b[off:off + incl]
        off += incl
        n += 1
        yield network, data
    print('packets: %d, linktype: %d' % (n, network), file=sys.stderr)


def extract_payload(network, data):
    """从二层/三层包里剥出 TCP 载荷（粗略：按 ip.proto==6 找 tcp 头）。"""
    if network == LINKTYPE_NULL:
        if len(data) < 4:
            return b''
        return data[4:]
    if network == LINKTYPE_ETHERNET:
        if len(data) < 14:
            return b''
        et = struct.unpack('>H', data[12:14])[0]
        off = 14
        while et in (0x8100, 0x88a8) and len(data) >= off + 4:
            et = struct.unpack('>H', data[off + 2:off + 4])[0]
            off += 4
        return data[off:]
    if network == LINKTYPE_RAW:
        return data
    if network == LINKTYPE_LINUX_SLL:
        return data[16:] if len(data) >= 16 else b''
    if network == LINKTYPE_LINUX_SLL2:
        # SLL2 头 20 字节：proto(2) reserved(2) ifindex(4) arphrd(2) pkttype(2) addrlen(2) addr(8)
        return data[20:] if len(data) >= 20 else b''
    return data


def tcp_payloads(pkt):
    """返回 [(sport, dport, payload)]，只取有完整 TCP 头的。"""
    out = []
    if len(pkt) < 20:
        return out
    ver = pkt[0] >> 4
    ihl = (pkt[0] & 0x0F) * 4
    if ver != 4:
        return out
    proto = pkt[9]
    if proto != 6:
        return out
    if len(pkt) < ihl + 20:
        return out
    total = struct.unpack('>H', pkt[2:4])[0]
    src = '.'.join(str(b) for b in pkt[12:16])
    dst = '.'.join(str(b) for b in pkt[16:20])
    t = pkt[ihl:]
    sport, dport = struct.unpack('>HH', t[0:4])
    doff = (t[12] >> 4) * 4
    if len(t) < doff:
        return out
    payload = t[doff:]
    # 用 IP 总长裁剪，避免抓到 Ethernet padding
    if total > ihl:
        want = total - ihl - doff
        if 0 <= want <= len(payload):
            payload = payload[:want]
    if payload:
        out.append((src, dst, sport, dport, payload))
    return out


def main():
    seen = OrderedDict()
    for network, data in read_pcap(PCAP):
        for src, dst, sport, dport, payload in tcp_payloads(extract_payload(network, data)):
            if not payload.startswith((b'GET ', b'POST ', b'HTTP/', b'PUT ', b'HEAD ')):
                continue
            key = payload[:400]
            seen.setdefault(key, (src, dst, sport, dport, payload))

    print('=== HTTP 流（去重 %d 条）===' % len(seen), file=sys.stderr)
    hosts = {}
    for key, (src, dst, sport, dport, payload) in seen.items():
        try:
            head = payload.split(b'\r\n\r\n', 1)[0].decode('utf-8', 'replace')
        except Exception:
            continue
        lines = head.split('\r\n')
        req = lines[0]
        hdr = {}
        for ln in lines[1:]:
            if ':' in ln:
                k, v = ln.split(':', 1)
                hdr[k.strip().lower()] = v.strip()
        host = hdr.get('host', '?')
        hosts.setdefault(host, []).append((req, hdr, payload))

    for host, items in hosts.items():
        print('\n######## HOST %s  (%d 条)' % (host, len(items)))
        for req, hdr, payload in items:
            print('  > %s' % req)
            print('    UA: %s' % hdr.get('user-agent', '')[:90])
            ck = hdr.get('cookie', '')
            if ck:
                print('    COOKIE: %s' % ck[:400])
            body = payload.split(b'\r\n\r\n', 1)[1] if b'\r\n\r\n' in payload else b''
            if body:
                print('    BODY: %s' % body[:500].decode('utf-8', 'replace').replace('\n', ' '))


if __name__ == '__main__':
    main()
