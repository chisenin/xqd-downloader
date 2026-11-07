# -*- coding: utf-8 -*-
import struct, os, zlib, marshal, io, sys
EXE = r'D:/Programs/学无止下载器-v1.5.0/LEL-downloader.exe'
d = open(EXE,'rb').read()
N = len(d)
mp = 2284140
plen, toc, toclen, pyvers = struct.unpack('!iiii', d[mp+8:mp+24])
lib = d[mp+24:mp+88].split(b'\x00')[0].decode()
# PKG 起始：TOC 绝对地址 - toc
pkgstart = (mp + 88) - plen
print('plen=%d toc=%d toclen=%d pyvers=%d lib=%s' % (plen,toc,toclen,pyvers,lib))
print('pkgstart 试探 =', pkgstart)
ap = pkgstart + toc
e0 = struct.unpack('!i', d[ap:ap+4])[0]
print('TOC 绝对位置 %d, 首个 entrylen=%d' % (ap, e0))
