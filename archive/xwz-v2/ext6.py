# -*- coding: utf-8 -*-
import struct, os, zlib
EXE = r'D:/Programs/学无止下载器-v1.5.0/LEL-downloader.exe'
OUT = 'out'; os.makedirs(OUT, exist_ok=True)
d = open(EXE,'rb').read()
mp = 2284140
plen, toc, toclen, pyvers = struct.unpack('!iiii', d[mp+8:mp+24])
pkgstart = (mp + 88) - plen
tocdata = d[pkgstart+toc: pkgstart+toc+toclen]

off = 0; ents = []
while off < len(tocdata):
    elen = struct.unpack('!i', tocdata[off:off+4])[0]
    if elen == 0: break
    body = tocdata[off+4:off+elen]
    pos, complen, datalen, flag, typcd = struct.unpack('!iIIBc', body[0:14])
    name = body[14:].split(b'\x00')[0].decode('utf-8','replace')
    ents.append((name,pos,complen,datalen,flag,typcd.decode()))
    off += elen
print('TOC 条目数:', len(ents))
for name,pos,cl,dl,fl,tc in ents:
    print('  %-44s type=%s flag=%d clen=%-8d dlen=%-8d' % (name,tc,fl,cl,dl))
    if tc in ('s','m','M','x','z','Z'):
        raw = d[pkgstart+pos: pkgstart+pos+cl]
        if fl & 0x01:
            try: raw = zlib.decompress(raw)
            except Exception as e: print('    解压失败', e)
        safe = name.replace('/','_').replace('\\','_')
        open(os.path.join(OUT,safe),'wb').write(raw)
print('\nout/ 文件数:', len(os.listdir(OUT)))
