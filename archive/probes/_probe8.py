# -*- coding: utf-8 -*-
import sys, os, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd, xqd_export as E

xqd.connect()
xml = xqd.open_course_list('调和养正太极营')
if not xml:
    print('打不开'); sys.exit()
xml = xqd.scroll_top(times=25)
cards = xqd.list_cards(xml)
print('卡片数:', len(cards))
tgt = None
for c in cards:
    if c['bx'] and c['by'] and c['by'] > 320:
        tgt = c; break
print('目标:', tgt['title'], tgt['when'], tgt['bx'], tgt['by'])
before = xqd.cache_state()
ids, changed = E.play_and_capture(tgt, before, timeout=25)
print('捕获 fileId:', ids, '清单:', changed)
if ids:
    links = E.collect_links()
    url = links.get(ids[0])
    print('URL:', url[:120] if url else None)
    if url:
        d, fn, q = E.split_dir_query(url)
        print('目录:', d)
        print('文件:', re.sub(r'^voddrm\.token\.[^.]*?\.','voddrm.token.<JWT>.',fn))
        # 拉 DRM 清单正文
        code, body = E.http_get(url, timeout=20)
        print('DRM清单 code=%s len=%d' % (code, len(body)))
        if code==200:
            t = body.decode('utf-8','replace')
            extinf = sum(float(x) for x in re.findall(r'#EXTINF:([\d.]+)', t))
            print('DRM清单 EXTINF合计=%.1fs 段数=%d' % (extinf, t.count('#EXTINF')))
            print('  前12行:'); print('   ', '\n    '.join(t.splitlines()[:12]))
            # 候选明文孪生
            cands = ['v.f%d.m3u8' % n for n in range(1440275, 1440300)]
            cands += [fn.replace('video_1440285_1.m3u8','v.f1440285.m3u8')]
            for cd in cands:
                cand = '%s%s?%s' % (d, cd, E.query_without(q))
                c2, b2 = E.http_get(cand, timeout=15)
                if c2==200 and b2.startswith(b'#EXTM3U'):
                    t2=b2.decode('utf-8','replace')
                    e2 = sum(float(x) for x in re.findall(r'#EXTINF:([\d.]+)', t2))
                    print('  孪生 %-18s len=%-6d EXTINF合计=%.1fs 段数=%d hasKEY=%s'
                          % (cd, len(b2), e2, t2.count('#EXTINF'), 'EXT-X-KEY' in t2))
