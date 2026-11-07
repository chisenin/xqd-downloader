# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd
xqd.connect()
xml = xqd.wake_app()
print('kind=', xqd.page_kind(xml), 'len=', len(xml))
for n in xqd.find_nodes(xml):
    if n['text']:
        print('   %-22s x=%-5d y=%-5d %r' % (n['id'].split('/')[-1], n['x'], n['y'], n['text'][:40]))
