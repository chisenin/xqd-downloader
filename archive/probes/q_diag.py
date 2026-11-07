# -*- coding: utf-8 -*-
"""诊断：列表页卡片解析的标题-日期配对是否正确。
输出每个日期行上方最近的文本节点及其距离。
"""
import sys, time
sys.path.insert(0, r'D:\.workbuddy\2026-11-06-20-15-25')
import sweep2 as S

S.connect()
xml = S.ui_dump()
print('kind=', S.page_kind(xml))
nodes = S.find_nodes(xml)
for n in nodes:
    t = (n['text'] or '').strip()
    if t:
        print('   x=%-4d y=%-5d %-44s' % (n['x'], n['y'], t[:42]))
