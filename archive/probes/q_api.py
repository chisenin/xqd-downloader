# -*- coding: utf-8 -*-
"""用 WebView cookie 的 rsessionId 试调业务 API，目标是拿到课程列表 JSON。"""
import urllib.request, urllib.parse, ssl, json, re, sys

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))

COOKIE = ('rsessionId=<RSESSION_ID>'
          '<RSESSION_ID_TAIL>; '
          'userId=<USER_ID>; cUserId=<C_USER_ID>; '
          'uid=<UID>; '
          'caller=app_edu; platform=android; ver=4260; deviceType=phone')

HOSTS = ['https://app.qianliao.net', 'https://m1.xqdaolove.cn',
         'https://m.qianliao.net', 'https://api.qianliao.net']

# 猜测的课程列表接口（campId 来自 H5 页面 URL）
CAMP = '5721891467'
PATHS = [
    '/app/course/getCourseList',
    '/app/financial/getCourseList',
    '/app/course/list',
    '/app/training/course/list',
    '/app/financial/course/list',
    '/api/course/list',
    '/app/camp/course/list',
    '/app/financial/training/courseList',
    '/app/financial/getCampCourseList',
    '/app/course/getLessonList',
]


def get(url, extra=''):
    h = {'User-Agent': 'okhttp/4.9.0',
         'Cookie': COOKIE,
         'Accept': 'application/json'}
    if extra:
        h.update(extra)
    req = urllib.request.Request(url, headers=h)
    try:
        r = OP.open(req, timeout=15)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300]
    except Exception as e:
        return None, str(e)[:160].encode()


for host in HOSTS:
    for p in PATHS:
        url = '%s%s?campId=%s' % (host, p, CAMP)
        st, body = get(url)
        if st == 200 and len(body) > 60:
            print('HIT %s -> %s  %d bytes' % (host, p, len(body)))
            print('   ', body[:260])
            print()
