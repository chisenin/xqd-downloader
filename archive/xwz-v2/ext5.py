# -*- coding: utf-8 -*-
import struct, os, zlib, marshal, io, sys
EXE = r'D:/Programs/学无止下载器-v1.5.0/LEL-downloader.exe'
OUT = 'out'; os.makedirs(OUT, exist_ok=True)
d = open(EXE,'rb').read()
mp = 2284140
plen, toc, toclen, pyvers = struct.unpack('!iiii', d[mp+8:mp+24])
pkgstart = (mp + 88) - plen
tocdata = d[pkgstart+toc: pkgstart+toc+toclen]

for mode in (0,1):
    off = 0; ents = []
    ok = True
    while off < len(tocdata):
        elen = struct.unpack('!i', tocdata[off:off+4])[0]
        if elen == 0: break
        if elen < 0 or off+4+elen > len(tocdata): ok=False; break
        body = tocdata[off+4:off+4+elen]
        try:
            pos, complen, datalen, flag, typcd = struct.unpack('!iIIBc', body[0:14])
        except Exception:
            ok=False; break
        name = body[14:].split(b'\x00')[0].decode('utf-8','replace')
        ents.append((name,pos,complen,datalen,flag,typcd.decode()))
        off += 4 + elen
    print('mode=%d 解析出 %d 条 ok=%s' % (mode, len(ents), ok))
    if len(ents) > 5:
        for e in ents[:8]:
            print('   %-46s type=%s flag=%d clen=%-8d dlen=%-8d' % (e[0],e[5],e[4],e[2],e[3]))
        if mode == 1:
            # 保存
            for name,pos,complen,datalen,flag,typcd in ents:
                if typcd not in ('s','z','Z','m','M','x'): continue
                raw = d[pkgstart+pos: pkgstart+pos+complen]
                if flag & 0x01:
                    try: raw = zlib.decompress(raw)
                    except Exception: pass
                safe = name.replace('/','_').replace('\\','_')
                open(os.path.join(OUT,safe),'wb').write(raw)
            print('已保存到 out/')
        break
