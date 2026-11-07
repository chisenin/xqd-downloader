# -*- coding: utf-8 -*-
"""实测：统计全部营的清单类型分布（media / master / drm / direct）。

目的：确认 xqd_engine 的 DRM 分支到底会不会被触发。
如果这批课里有 DRM 课，而 xqd_engine 不找明文孪生，
那么 GUI 下载这些课会拿到加密分片 → 成品是坏的。

抽样策略：每个营取前 N 节 + 中间 M 节（避免只测到开头）。
每节只拉清单（HEAD/GET 一次），不下载分片。
"""
import os
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import xqd_platform as P
import xqd_engine as E

COOKIE = ('rsessionId=<RSESSION_ID>'
          '<RSESSION_ID_TAIL>; '
          'userId=<USER_ID>; cUserId=<C_USER_ID>; '
          'uid=<UID>; '
          'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')

SAMPLE = int(os.environ.get('SAMPLE', '6'))


def pick(lessons, n):
    """取前 n 节 + 中间 n 节 + 后 n 节。"""
    total = len(lessons)
    if total <= n:
        return list(lessons)
    idxs = list(range(n))
    mid = total // 2
    idxs += list(range(mid, mid + n))
    idxs += list(range(total - n, total))
    seen = set()
    out = []
    for i in idxs:
        if 0 <= i < total and i not in seen:
            seen.add(i)
            out.append(lessons[i])
    return out


def main():
    plat = P.QianliaoPlatform(cookie=COOKIE)
    grand = collections.Counter()
    for kind in ('正式营', '体验营'):
        camps = plat.list_camps(kind)
        print('==== %s：%d 个营 ====' % (kind, len(camps)))
        for camp in camps:
            try:
                lessons = plat.camp_catalog(camp)
            except Exception as e:
                print('  %-28s 课表失败：%s' % (camp.name, e))
                continue
            cnt = collections.Counter()
            details = []
            for le in pick(lessons, SAMPLE):
                try:
                    url = plat.resolve(camp, le)
                except Exception as e:
                    cnt['resolve_fail'] += 1
                    details.append('%s -> 解析失败' % le.title)
                    continue
                code, body = E.http_get(url, timeout=30)
                if code != 200:
                    cnt['http_%s' % code] += 1
                    details.append('%s -> HTTP %s' % (le.title, code))
                    continue
                if not body.startswith(b'#EXTM3U'):
                    cnt['direct'] += 1
                    details.append('%s -> 直链(%s)' % (
                        le.title, os.path.splitext(url.split('?')[0])[1]))
                    continue
                text = body.decode('utf-8', 'replace')
                if 'EXT-X-STREAM-INF' in text:
                    cnt['master'] += 1
                    details.append('%s -> master' % le.title)
                elif 'EXT-X-KEY' in text:
                    cnt['drm'] += 1
                    details.append('%s -> *** DRM ***' % le.title)
                else:
                    cnt['media'] += 1
                    details.append('%s -> media' % le.title)
            grand.update(cnt)
            print('  %-28s 共%3d节 抽样%d: %s'
                  % (camp.name, len(lessons), sum(cnt.values()),
                     dict(cnt)))
            for d in details:
                if 'DRM' in d or 'resolve_fail' in d or 'HTTP' in d:
                    print('      %s' % d)
    print('\n==== 汇总 ====')
    print(dict(grand))
    if grand.get('drm'):
        print('\n★ 存在 DRM 课 —— xqd_engine 必须接明文孪生逻辑')
    else:
        print('\n○ 本次抽样未遇到 DRM 课')


if __name__ == '__main__':
    main()
