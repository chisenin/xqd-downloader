import export_courses as E
import os, re

E.connect()
st = E._cache_state()
names = [f for f in st if f.startswith('.') and 'hls' in f]
print('manifest count:', len(names))
print('sample:', names[:8])

# 取一个真实存在的
for f in names:
    txt = E._read_remote_manifest(f)
    if txt.strip():
        print('--- file:', f, 'len', len(txt))
        print('   content head:', txt[:200].replace('\n', ' | '))
        ids = E._biz_ids(txt)
        print('   biz ids:', ids)
        md5name = f.lstrip('.')
        print('   md5 of filename:', md5name)
        # 检验 md5 是否等于 URL 的 md5
        import hashlib
        for u in re.findall(r'https?://[^\s"\']+', txt):
            print('   md5(url) =', hashlib.md5(u.encode()).hexdigest())
            print('   md5(url no query) =', hashlib.md5(u.split('?')[0].encode()).hexdigest())
        break

# 检查所有文件的 mtime 分布
print('--- newest 8 by mtime ---')
srt = sorted(st.items(), key=lambda kv: -kv[1][0])[:8]
for f, (mt, sz) in srt:
    print('   %-40s mtime=%d size=%d' % (f, mt, sz))
