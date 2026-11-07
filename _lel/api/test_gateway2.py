# -*- coding: utf-8 -*-
"""打印实际响应体，判断 200 到底是 JSON 还是 HTML 前端页。

同时按前端封装的真实形态组合 host：
    URL  = <origin>/financial/api/transfer/gate/<endpoint>
    Body = {"transferData": {...}}
"""
import os
import sys
import ssl
import urllib.request
import urllib.error
import json
import itertools

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))

# ★ 凭据不在源码里 —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import xqd_creds            # noqa: E402

COOKIE = xqd_creds.load_cookie()

CAMP = '5721891467'


def raw_get(url, referer='https://m.qianliao.net/', ua=None):
    h = {'User-Agent': ua or ('Mozilla/5.0 (Linux; Android 12; M2102K1C) okhttp/4.9.0'),
         'Cookie': COOKIE,
         'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://m.qianliao.net',
         'Referer': referer}
    req = urllib.request.Request(url, headers=h)
    try:
        r = OP.open(req, timeout=20)
        return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return None, str(e).encode(), {}


def raw_post(url, body, referer='https://m.qianliao.net/', ua=None, ctype='application/json;charset=UTF-8'):
    h = {'User-Agent': ua or ('Mozilla/5.0 (Linux; Android 12; M2102K1C) okhttp/4.9.0'),
         'Cookie': COOKIE,
         'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://m.qianliao.net',
         'Referer': referer,
         'Content-Type': ctype}
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=h, method='POST')
    try:
        r = OP.open(req, timeout=20)
        return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return None, str(e).encode(), {}


def classify(resp):
    try:
        t = resp.decode('utf-8', 'replace').lstrip()
    except Exception:
        return 'BIN', ''
    if t.startswith('{') or t.startswith('['):
        return 'JSON', t[:400]
    if t.startswith('<'):
        # 取 <title>
        import re
        m = re.search(r'<title>(.*?)</title>', t, re.S | re.I)
        return 'HTML', ('title=' + (m.group(1).strip() if m else '?')) + ' len=%d' % len(t)
    return 'TEXT', t[:200]


print('### 1) GET 首页，看 m.qianliao.net 到底返回什么 ###')
for host in ['m.qianliao.net', 'app.qianliao.net']:
    st, resp, hd = raw_get('https://%s/' % host)
    k, s = classify(resp)
    print('  GET %-22s -> %s  %-6s %s' % (host, st, k, s[:180]))

print()
print('### 2) POST transfer 网关（前端真实形态），看响应类型 ###')
EP = '/gate/course/playListOfCourse'
BODY = {'transferData': {'campId': CAMP, 'onlyCourseCatalogue': True}}
for host in ['m.qianliao.net', 'app.qianliao.net', 'm1.xqdaolove.com',
             'm1.xqdaolove.cn', 'm1.xqdaolove.cn']:
    url = 'https://%s/financial/api/transfer%s' % (host, EP)
    st, resp, hd = raw_post(url, BODY)
    k, s = classify(resp)
    print('  %-22s -> %s  %-6s %s' % (host, st, k, s[:200]))
    if k == 'JSON':
        print('     FULL:', resp[:1200].decode('utf-8', 'replace'))

print()
print('### 3) 试其它已知前端端点（看哪个返回 JSON）###')
CANDS = [
    ('/gate/course/myCourseList', {'transferData': {'page': {'page': 1, 'size': 20}}}),
    ('/gate/course/myCourseListV2', {'transferData': {'clientType': 'app'}}),
    ('/gate/course/getSimpleCampDetail', {'transferData': {'campId': CAMP}}),
    ('/gate/smallCourse/smallCourseTopicList', {'transferData': {'courseId': CAMP}}),
    ('/gate/openCourse/playListOfCourse', {'transferData': {'periodId': '1'}}),
]
for ep, body in CANDS:
    for host in ['m.qianliao.net', 'app.qianliao.net']:
        st, resp, hd = raw_post('https://%s/financial/api/transfer%s' % (host, ep), body)
        k, s = classify(resp)
        tag = '  <<< JSON' if k == 'JSON' else ''
        print('  %-18s %-46s -> %s %-6s %s%s' % (host, ep, st, k, s[:110], tag))
        if k == 'JSON':
            print('     FULL:', resp[:1500].decode('utf-8', 'replace'))
            break
