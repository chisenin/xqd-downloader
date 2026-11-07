# -*- coding: utf-8 -*-
"""决定性实验：拿 App 抓包得到的真实 Cookie，打通兴趣岛业务网关。

背景（见 docs/01-已验证事实.md）：
  网关 = POST https://<host>/financial/api/transfer/gate/<endpoint>
  Body = {"transferData": {...}}
  未登录 -> code:110 无权限访问

本脚本只做「同 Cookie × 不同 host × 不同 endpoint」的最小探测，
目标是找到返回 code:0 的组合，不做无谓的宽泛扫描。
"""
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

COOKIE = ('rsessionId=<RSESSION_ID>'
          '<RSESSION_ID_TAIL>; '
          'userId=<USER_ID>; cUserId=<C_USER_ID>; '
          'uid=<UID>; '
          'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')

UA_APP = 'Mozilla/5.0 (Linux; Android 12; M2102K1C) okhttp/4.9.0'
CAMP = '5721891467'


def call(host, path, body=None, method='POST', timeout=20):
    url = 'https://%s%s' % (host, path)
    h = {'User-Agent': UA_APP,
         'Cookie': COOKIE,
         'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://%s' % host,
         'Referer': 'https://%s/financial/training-intro' % host}
    data = None
    if body is not None:
        h['Content-Type'] = 'application/json;charset=UTF-8'
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        r = OP.open(req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:500]
    except Exception as e:
        return None, str(e)[:200].encode()


def preview(resp):
    try:
        t = resp.decode('utf-8', 'replace')
    except Exception:
        return repr(resp[:120])
    return t.replace('\n', ' ')[:260]


def code_of(resp):
    try:
        return json.loads(resp.decode('utf-8', 'replace')).get('code')
    except Exception:
        return None


HOSTS = ['m.qianliao.net', 'app.qianliao.net', 'm1.xqdaolove.com',
         'm1.xqdaolove.cn', 'm1.qianliao.net']

# 网关路径前缀（transfer 转发模式）
PREFIXES = ['/financial/api/transfer/gate', '/api/transfer/gate', '/transfer/gate']

# 端点：先试 list 类（对 campId 依赖小），再试 playList
ENDPOINTS = [
    ('/course/myCourseList', {'page': {'page': 1, 'size': 20}}),
    ('/course/myCourseListV2', {'clientType': 'app'}),
    ('/course/playListOfCourse', {'campId': CAMP, 'onlyCourseCatalogue': True}),
]

print('=== A. transfer 网关（转发模式，Body=transferData）===')
for host, prefix, (ep, td) in itertools.product(HOSTS, PREFIXES, ENDPOINTS):
    st, resp = call(host, prefix + ep, {'transferData': td})
    c = code_of(resp)
    flag = '*** code=0 ***' if c == 0 else ''
    print('  %-20s%-28s%-34s -> %s code=%s %s'
          % (host, prefix, ep, st, c, flag))
    if c == 0:
        print('    BODY:', preview(resp))
        print('    >>> HIT: %s%s' % (host, prefix + ep))
        break

print()
print('=== B. 直接 POST /gate/...（旧脚本假设）===')
for host, (ep, td) in itertools.product(HOSTS, ENDPOINTS):
    st, resp = call(host, '/gate' + ep, td)
    c = code_of(resp)
    flag = '*** code=0 ***' if c == 0 else ''
    print('  %-20s%-40s -> %s code=%s %s' % (host, '/gate' + ep, st, c, flag))
    if c == 0:
        print('    BODY:', preview(resp))
        break
