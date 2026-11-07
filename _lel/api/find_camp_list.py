# -*- coding: utf-8 -*-
"""找「正式营/体验营」列表端点。

已知：前端 myCourseListV2 的 body 带 skyType:"FINANCIAL"（正式营），
但走的是 transferApiSite:"ufwApi" 这一套封装（与 ot.a 那一套不同）。

策略：不猜网关，而是**枚举端点 × 枚举 body 变体**，看哪个返回含
campName / courseTotalNum 的营列表。
"""
import ssl
import urllib.request
import urllib.error
import json

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))

COOKIE = ('rsessionId=<RSESSION_ID>'
          '<RSESSION_ID_TAIL>; '
          'userId=<USER_ID>; cUserId=<C_USER_ID>; '
          'uid=<UID>; '
          'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')
HOST = 'm.qianliao.net'
UA = 'Mozilla/5.0 (Linux; Android 12; M2102K1C) okhttp/4.9.0'

# 候选网关前缀
PREFIXES = [
    '/financial/api/transfer',
    '/financial/api/ufw/transfer',
    '/financial/api/ufwApi/transfer',
    '/ufw/financial/api/transfer',
    '/financial/ufw/api/transfer',
    '/financial/api',
]


def post(prefix, path, td):
    url = 'https://%s%s%s' % (HOST, prefix, path)
    body = json.dumps({'transferData': td}).encode()
    h = {'User-Agent': UA, 'Cookie': COOKIE,
         'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://%s' % HOST,
         'Referer': 'https://%s/' % HOST,
         'Content-Type': 'application/json;charset=UTF-8'}
    req = urllib.request.Request(url, data=body, headers=h, method='POST')
    try:
        r = OP.open(req, timeout=15)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200]
    except Exception as e:
        return None, str(e)[:120].encode()


def summarize(resp):
    try:
        js = json.loads(resp.decode('utf-8', 'replace'))
    except Exception:
        return None, resp[:80]
    st = js.get('state') or {}
    data = js.get('data')
    keys = list(data.keys())[:10] if isinstance(data, dict) else type(data).__name__
    n = ''
    if isinstance(data, dict):
        for k in ('courses', 'list', 'records'):
            if isinstance(data.get(k), list):
                n = ' %s=%d' % (k, len(data[k]))
    return st.get('code'), '%s%s keys=%s' % (st.get('msg'), n, keys)


def try_camp_list():
    """营列表端点候选 + body 变体。"""
    bodies = [
        ('skyType=FINANCIAL', {'skyType': 'FINANCIAL', 'page': {'page': 1, 'size': 200}}),
        ('skyType=INTENTION', {'skyType': 'INTENTION', 'page': {'page': 1, 'size': 200}}),
        ('page only', {'page': {'page': 1, 'size': 200}}),
        ('type=FINANCIAL', {'type': 'FINANCIAL', 'page': {'page': 1, 'size': 200}}),
        ('skyType=EXPERIENCE', {'skyType': 'EXPERIENCE', 'page': {'page': 1, 'size': 200}}),
    ]
    eps = ['/gate/course/myCourseListV2', '/gate/course/myCourseList',
           '/gate/course/myFinancialCourseList', '/gate/financialCamp/myFinancialCampList',
           '/gate/course/myCampList']
    hits = []
    for prefix in PREFIXES:
        for ep in eps:
            for tag, td in bodies:
                st, resp = post(prefix, ep, td)
                if st != 200:
                    continue
                code, summary = summarize(resp)
                if code == 0:
                    print('  HIT %-28s %-38s %-20s -> %s' % (prefix, ep, tag, summary))
                    hits.append((prefix, ep, td))
                elif 'html' not in summary.lower():
                    print('      %-26s %-36s %-18s -> code=%s %s'
                          % (prefix.split('/financial')[1] or prefix, ep, tag, code, summary))
    return hits


def main():
    print('### 1) 枚举营列表端点 × body 变体 ###')
    hits = try_camp_list()

    print('\n### 2) 已知可用：myCourseListV2 无 skyType（返回公开课） ###')
    st, resp = post('/financial/api/transfer', '/gate/course/myCourseListV2', {})
    js = json.loads(resp.decode('utf-8', 'replace'))
    courses = (js.get('data') or {}).get('courses', [])
    print('  courses=%d' % len(courses))
    for c in courses[:3]:
        print('    campName=%s periodId=%s skuType=%s total=%s'
              % (c.get('campName'), c.get('periodId'), c.get('skuType'),
                 c.get('courseTotalNum')))

    print('\n### 3) 试 skyType=FINANCIAL + 不同前缀（重点） ###')
    td = {'skyType': 'FINANCIAL', 'page': {'page': 1, 'size': 200}}
    for prefix in PREFIXES:
        st, resp = post(prefix, '/gate/course/myCourseListV2', td)
        code, summary = summarize(resp) if st == 200 else (st, resp[:100])
        print('  %-30s -> %s  %s' % (prefix, code, summary))


if __name__ == '__main__':
    main()
