# -*- coding: utf-8 -*-
"""手写 PyInstaller 提取器（Python 3.7 / PyInstaller 4.x 格式）。"""
import os, sys, struct, zlib, marshal, io

EXE = r'D:/Programs/学无止下载器-v1.5.0/LEL-downloader.exe'
d = open(EXE, 'rb').read()
MAGIC = b'MEI\x0c\x0b\x0a\x0b\x0e'
pkgpos = d.find(MAGIC)
print('pkgpos', pkgpos)

# CArchive: cookie 在 MAGIC 之后
cookie = d[pkgpos:pkgpos+24]
print('cookie', cookie)
namesize = struct.unpack('!i', cookie[8:12])[0]
pkgstart = struct.unpack('!i', cookie[12:16])[0]
tocpos = struct.unpack('!i', cookie[16:20])[0]
toclen  = struct.unpack('!i', cookie[20:24])[0]
print('pkgstart',pkgstart,'tocpos',tocpos,'toclen',toclen,'namesize',namesize)

# TOC: 每项 len(entry) 结构
# (entrylen, pos, complen, datalen, flag, typcd, name[namesize])
p = pkgstart + tocpos
toc = d[p:p+toclen]
out = {}
off = 0
entries = []
while off < len(toc):
    entrylen = struct.unpack('!i', toc[off:off+4])[0]
    if entrylen <= 0 or off+entrylen > len(toc):
        break
    body = toc[off+4:off+entrylen]
    pos, complen, datalen, flag, typcd = struct.unpack('!iiIIc', body[:13])
    name = body[13:].split(b'\x00')[0].decode('utf-8','replace')
    entries.append((name, pos, complen, datalen, flag, typcd))
    off += entrylen

print('TOC 条目数:', len(entries))
for name,pos,cl,dl,fl,tc in entries:
    if tc in (b's', b'm', b'M', b'z', b'Z'):
        print('  %-46s type=%s complen=%d datalen=%d' % (name, tc.decode(), cl, dl))
