# -*- coding: utf-8 -*-
import os
import sys
import ssl, urllib.request, urllib.error, json, urllib.parse
CTX=ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=CTX))
# ★ 凭据不在源码里 —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import xqd_creds            # noqa: E402

COOKIE = xqd_creds.load_cookie()

host='m.qianliao.net'
h={'User-Agent':'Mozilla/5.0 (Linux; Android 12) Chrome/120 Mobile Safari/537.36',
   'Cookie':COOKIE,'Accept':'application/json, text/plain, */*',
   'Referer':'https://%s/financial/training-intro'%host,'Origin':'https://%s'%host}
req=urllib.request.Request('https://%s/financial/api/gate/course/myCourseListV2'%host,headers=h)
try:
    OP.open(req,timeout=20)
except urllib.error.HTTPError as e:
    body=e.read()
d=json.loads(body)
url=d['data']['url']
print('=== 403 data.url 原文 ===')
print(url[:400])
print()
inner=urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('redirect_url',[''])[0]
print('=== redirect_url 解码 ===')
print(urllib.parse.unquote(inner))
