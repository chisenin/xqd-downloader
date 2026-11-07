# -*- coding: utf-8 -*-
import struct, os, sys
EXE = r'D:/Programs/学无止下载器-v1.5.0/LEL-downloader.exe'
d = open(EXE,'rb').read()
N = len(d)
MAGIC = b'MEI\x0c\x0b\x0a\x0b\x0e'
cands = []
i = 0
while True:
    j = d.find(MAGIC, i)
    if j < 0: break
    cands.append(j)
    i = j+1
print('MAGIC 候选位置:', cands)
for mp in cands:
    # cookie: magic(8) len(4) toc(4) toclen(4) pyvers(4) pylibname(64)
    if mp+88 > N: continue
    plen, toc, toclen, pyvers = struct.unpack('!iiii', d[mp+8:mp+24])
    lib = d[mp+24:mp+88].split(b'\x00')[0]
    print('\n候选 @%d: len=%d toc=%d toclen=%d pyvers=%d lib=%r' % (mp,plen,toc,toclen,pyvers,lib))
    if 0 < toclen < 5_000_000 and 0 < toc < N:
        pkgstart = mp - (plen - toclen - toc)  # 不确定
        print('   试探 pkgstart 计算…')
        # 常见：PKG 起始 = toc绝对位置 - toc
        for base in (mp, mp - (plen - toclen)):
            ap = base + toc
            if 0 < ap < N-20:
                e0 = struct.unpack('!i', d[ap:ap+4])[0]
                print('   base=%d -> ap=%d entrylen=%d' % (base, ap, e0))
