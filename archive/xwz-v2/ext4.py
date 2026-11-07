# -*- coding: utf-8 -*-
import struct, os, zlib, marshal, io, sys, traceback
EXE = r'D:/Programs/学无止下载器-v1.5.0/LEL-downloader.exe'
OUT = 'out'
os.makedirs(OUT, exist_ok=True)
d = open(EXE,'rb').read()
mp = 2284140
plen, toc, toclen, pyvers = struct.unpack('!iiii', d[mp+8:mp+24])
namesize = 64
pkgstart = (mp + 88) - plen
ap = pkgstart + toc
tocdata = d[ap:ap+toclen]

off = 0
entries = []
while off < len(tocdata):
    elen = struct.unpack('!i', tocdata[off:off+4])[0]
    if elen <= 0 or off+elen > len(tocdata): break
    body = tocdata[off+4:off+elen]
    pos, complen, datalen, flag, typcd = struct.unpack('!iiIIc', body[:13])
    name = body[13:13+namesize].split(b'\x00')[0].decode('utf-8','replace')
    entries.append((name, pos, complen, datalen, flag, typcd.decode()))
    off += elen
print('TOC 条目数:', len(entries))
for e in entries:
    print('  %-48s type=%s flag=%d complen=%-9d datalen=%-9d' % (e[0], e[5], e[4], e[2], e[3]))

# 提取所有条目
manifest = []
for name, pos, complen, datalen, flag, typcd in entries:
    if typcd in ('s','z','Z','m','M','x'):
        raw = d[pkgstart+pos: pkgstart+pos+complen]
        try:
            if flag & 0x01:
                raw = zlib.decompress(raw)
        except Exception as e:
            pass
        safe = name.replace('/','_').replace('\\','_')
        if typcd == 's' or typcd == 'm' or typcd == 'M':
            fn = os.path.join(OUT, safe)
            open(fn,'wb').write(raw)
            manifest.append((name, typcd, len(raw), fn))
print('\n已保存 %d 个文件' % len(manifest))
for m in manifest:
    if m[0].endswith('.pyc') or 'main' in m[0].lower():
        print('  ', m)
