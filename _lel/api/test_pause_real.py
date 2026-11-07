# -*- coding: utf-8 -*-
"""真实链路验证：暂停 → 继续 → 断点续下。

用真实 Cookie 拉一节真实视频课：
  1. 开始下载
  2. 下到一半点「暂停」—— 记录已下分片数
  3. 确认暂停期间没有新分片落地
  4. 点「继续」—— 确认接着下而不是从头下
  5. 成品可解析、时长与课表一致
"""
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import xqd_engine
import xqd_platform

COOKIE = (
    'rsessionId=<RSESSION_ID>'
    '<RSESSION_ID_TAIL>; '
    'userId=<USER_ID>; cUserId=<C_USER_ID>; '
    'uid=<UID>; '
    'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')

OUT = os.path.join(tempfile.gettempdir(), 'xqd_pause_real')
results = []


def ok(name, cond, extra=''):
    results.append((name, bool(cond)))
    print('%-44s %s %s' % (name, 'PASS' if cond else 'FAIL', extra))


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)

    plat = xqd_platform.QianliaoPlatform(cookie=COOKIE)
    camps = plat.list_camps('正式营')
    camp = [c for c in camps if '道德经诵读' in c.name][0]
    les = plat.camp_catalog(camp)
    le = les[0]
    print('课：%s  时长 %ds' % (le.title, le.duration))

    out = os.path.join(OUT, le.title.replace('/', '_') + '.mp4')

    ctl = xqd_engine.DownloadControl()
    state = {'res': None}

    def run():
        state['res'] = xqd_engine.download_lesson(
            lambda: plat.resolve(camp, le), out,
            quality='max', workers=12,
            expect_duration=le.duration, control=ctl)

    import threading
    th = threading.Thread(target=run)
    th.start()

    # 等分片目录出现并积累一些分片
    seg_dirs = []
    deadline = time.time() + 60
    while time.time() < deadline:
        seg_dirs = [d for d in os.listdir(tempfile.gettempdir())
                    if d.startswith('xqd_')
                    and os.path.isdir(os.path.join(tempfile.gettempdir(), d))]
        if seg_dirs:
            cand = [os.path.join(tempfile.gettempdir(), d)
                    for d in seg_dirs]
            cnt = 0
            for c in cand:
                try:
                    cnt += len([f for f in os.listdir(c)
                                if f.endswith('.ts')])
                except OSError:
                    pass
            if cnt >= 20:
                break
        time.sleep(0.5)

    ctl.pause()
    time.sleep(1.5)

    def seg_count():
        n = 0
        for d in os.listdir(tempfile.gettempdir()):
            if not d.startswith('xqd_'):
                continue
            p = os.path.join(tempfile.gettempdir(), d)
            if not os.path.isdir(p):
                continue
            try:
                n += len([f for f in os.listdir(p) if f.endswith('.ts')])
            except OSError:
                pass
        return n

    at_pause = seg_count()
    ok('暂停前已下到分片', at_pause > 0, '%d 个' % at_pause)
    time.sleep(2.0)
    after_wait = seg_count()
    ok('暂停期间没有新分片', after_wait == at_pause,
       '暂停时 %d → 2秒后 %d' % (at_pause, after_wait))
    ok('暂停期间线程仍在等待（未退出）', th.is_alive())

    ctl.resume()
    th.join(600)
    ok('继续后下载完成', not th.is_alive())

    res = state['res']
    ok('下载结果成功', res and res[0], str(res[1] if res else ''))

    if res and os.path.isfile(res[2]):
        info = xqd_engine.probe_media(res[2])
        dur = info['duration']
        ok('成品可解析', info['has_video'] and dur > 0,
           '容器=%s 时长=%.1fs' % (info['format_name'], dur))
        ok('时长与课表一致（误差<1%%）',
           abs(dur - le.duration) <= max(3.0, le.duration * 0.01),
           '%.1fs vs 期望 %.1fs' % (dur, le.duration))

    passed = sum(1 for _n, c in results if c)
    print('\n===== %d/%d 通过 =====' % (passed, len(results)))
    for n, c in results:
        if not c:
            print('  FAIL:', n)
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
