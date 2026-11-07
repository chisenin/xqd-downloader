# -*- coding: utf-8 -*-
import marshal, zlib, struct, os
raw = open('out/PYZ-00.pyz','rb').read()
toc = marshal.loads(raw[1944903:])
os.makedirs('pyz', exist_ok=True)
saved = []
for name,(typ,pos,length) in toc:
    blob = raw[pos:pos+length]
    if typ == 1:
        try: blob = zlib.decompress(blob)
        except Exception: continue
    safe = name.replace('.','__')
    open(os.path.join('pyz',safe+'.pyc'),'wb').write(blob)
    saved.append((name,typ,len(blob)))
print('提取 %d 个模块' % len(saved))
# 只打印看起来是本项目的
for n,t,l in saved:
    if not n.startswith(('_','Crypto','urllib','certifi','idna','pkg_resources','setuptools','pip','attr','jaraco')):
        print('  %-42s type=%d len=%d' % (n,t,l))
