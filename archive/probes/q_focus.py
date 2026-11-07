# -*- coding: utf-8 -*-
"""诊断：点击「去学习」后到底发生了什么（焦点窗口 / 是否播放器浮窗）。"""
import sys, os, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xqd

xqd.connect()
ADB = xqd.ADB


def sh(cmd):
    p = subprocess.run([ADB, '-s', xqd.DEVICE, 'shell', cmd],
                       capture_output=True, timeout=60)
    return p.stdout.decode('utf-8', 'replace')


print('--- 焦点窗口 ---')
print(sh("dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp' | head -4"))
print('--- 前台 Activity ---')
print(sh("dumpsys activity activities | grep -m4 -E 'ResumedActivity|topResumedActivity'"))

xml = xqd.ui_dump()
print('\n当前 kind =', xqd.page_kind(xml))
cards = xqd.list_cards(xml)
vis = [c for c in cards if c['bx']]
print('可见卡 %d / 共 %d' % (len(vis), len(cards)))
for c in vis:
    print('   btn=(%s,%s) %-44s %s' % (c['bx'], c['by'], c['title'][:42], c['when']))

if vis:
    tgt = vis[0]
    print('\n点击 → %s' % tgt['title'])
    before = xqd.cache_state()
    xqd.tap(tgt['bx'], tgt['by'])
    time.sleep(3)
    print('3s 后 focus:', sh("dumpsys window windows | grep -m1 'mCurrentFocus'").strip())
    time.sleep(5)
    xml = xqd.ui_dump()
    print('8s 后 kind =', xqd.page_kind(xml))
    print('   focus:', sh("dumpsys window windows | grep -m1 'mCurrentFocus'").strip())
    after = xqd.cache_state()
    ch = [f for f in after if f.startswith('.') and 'hls' in f
          and (f not in before or before[f][0] != after[f][0])]
    print('清单变化 %d:' % len(ch))
    for f in ch:
        print('   %-42s %s' % (f, xqd.biz_ids(xqd.read_manifest(f))))
    if xqd.page_kind(xml) == 'player':
        print('\n--- 播放器页 nameTv ---')
        for n in xqd.find_nodes(xml):
            if n['id'].endswith('/nameTv'):
                print('   %-46s (%d,%d)' % (n['text'][:44], n['x'], n['y']))
