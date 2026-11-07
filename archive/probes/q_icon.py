# -*- coding: utf-8 -*-
"""找「课程」图标的 resource-id：在营详情页上滚后 dump 全量节点。"""
import sys, time, re
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import export_courses as E

E.connect()
xml = E.ui_dump()
print('kind=', E._page_kind(xml))
print('--- 含 课程 的节点 ---')
for m in re.finditer(r'<node[^>]*>', xml):
    s = m.group(0)
    if 'text="课程"' in s or 'course' in s.lower():
        print('  ', s[:300])
print('--- tvName/其它 id 汇总 ---')
ids = {}
for n in E.find_nodes(xml):
    i = n.get('id', '')
    if i:
        ids[i] = ids.get(i, 0) + 1
for k, v in sorted(ids.items(), key=lambda kv: -kv[1])[:30]:
    print('   %-52s x%d' % (k, v))
