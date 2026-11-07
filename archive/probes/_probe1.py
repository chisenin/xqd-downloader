# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd
xqd.connect()
xml = xqd.wake_app()
print('page_kind =', xqd.page_kind(xml))
xml = xqd.open_learning()
print('after open_learning kind =', xqd.page_kind(xml))
print('LEN', len(xml))
for n in xqd.find_nodes(xml):
    if n['text']:
        print('  id=%-46s x=%-5d y=%-5d %r' % (n['id'][-46:], n['x'], n['y'], n['text'][:40]))
