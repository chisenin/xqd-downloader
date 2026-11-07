# -*- coding: utf-8 -*-
"""扫描 App 所有数据库，找出含 biz fileId 或课名的关联表。"""
import sys, re, time
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()

DBS = [
    '/data/data/com.qlchat.xingqudao/databases/qlChatCourses.db',
    '/data/data/com.qlchat.xingqudao/databases/AndroidAria.db',
]
for db in DBS:
    print('\n######## %s' % db)
    tabs = S.adb('shell', "sqlite3 %s '.tables'" % db, timeout=60).stdout or ''
    tl = [t.strip() for t in tabs.split() if t.strip()]
    print('tables(%d): %s' % (len(tl), ' '.join(tl)))
    for t in tl:
        sch = S.adb('shell', "sqlite3 %s '.schema %s'" % (db, t), timeout=60).stdout or ''
        cols = re.findall(r'\b(\w+)\s+(?:TEXT|VARCHAR|INTEGER|INT)', sch)
        hits = [c for c in cols if re.search(
            r'video|file|name|title|lesson|course|url|camp', c, re.I)]
        if hits:
            n = S.adb('shell', "sqlite3 %s 'select count(*) from %s'" % (db, t),
                      timeout=60).stdout.strip()
            print('  -- %-28s rows=%-6s 命中列: %s' % (t, n, ','.join(hits)))
            for c in hits[:4]:
                vals = S.adb('shell', "sqlite3 -separator '|' %s "
                             "'select %s from %s limit 4'" % (db, c, t),
                             timeout=60).stdout or ''
                for v in vals.strip().splitlines()[:3]:
                    print('        %s = %s' % (c, v[:110]))
