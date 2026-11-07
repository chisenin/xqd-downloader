# -*- coding: utf-8 -*-
"""打通 getCoursePlayUrl：拿真实 m3u8 播放地址，并核对 DRM 孪生规则。

已确认的前端契约（见 _lel/api/course_api_context.txt）：
  POST https://m.qianliao.net/financial/api/transfer/gate/course/getCoursePlayUrl
  Body: {"transferData": {videoHost, roomId, topicId, businessId, businessType}}
        businessType = "camp"（正课） | "OPEN_COURSE"（公开课）
  返回: data.coursePlayUrl
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
GATE = 'https://%s/financial/api/transfer' % HOST
UA = 'Mozilla/5.0 (Linux; Android 12; M2102K1C) okhttp/4.9.0'


def api(path, transfer_data, timeout=25):
    body = json.dumps({'transferData': transfer_data}).encode()
    h = {'User-Agent': UA, 'Cookie': COOKIE,
         'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://%s' % HOST,
         'Referer': 'https://%s/' % HOST,
         'Content-Type': 'application/json;charset=UTF-8'}
    req = urllib.request.Request(GATE + path, data=body, headers=h, method='POST')
    try:
        r = OP.open(req, timeout=timeout)
        return r.status, json.loads(r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400]
    except Exception as e:
        return None, str(e)[:200]


def show(tag, st, js):
    if isinstance(js, (bytes, str)):
        print('  %-28s -> %s  %s' % (tag, st, str(js)[:200]))
        return
    stt = js.get('state', {})
    print('  %-28s -> %s  code=%s msg=%s' % (tag, st, stt.get('code'), stt.get('msg')))
    return js.get('data')


CAMP = '5721891467'

print('### A. playListOfCourse 拿 topicId ###')
st, js = api('/gate/course/playListOfCourse', {'campId': CAMP, 'onlyCourseCatalogue': True})
data = show('playListOfCourse', st, js)
if not isinstance(data, dict):
    raise SystemExit('拿不到课程表')
courses = data.get('courses', [])
print('  课程数: %d' % len(courses))
for c in courses[:5]:
    print('    topicId=%-14s type=%-6s dur=%-6s playUrl=%-22s name=%s'
          % (c.get('topicId'), c.get('type'), c.get('duration'),
             c.get('playUrl'), c.get('name')))

print()
print('### B. getCoursePlayUrl（businessType=camp）###')
for c in courses[:4]:
    td = {'videoHost': None, 'roomId': c.get('roomId'),
          'topicId': c.get('topicId'), 'businessId': CAMP,
          'businessType': 'camp'}
    st, js = api('/gate/course/getCoursePlayUrl', td)
    d = show('%s' % (c.get('name') or '')[:26], st, js)
    if isinstance(d, dict):
        print('      data 键: %s' % list(d.keys()))
        print('      coursePlayUrl: %s' % json.dumps(d.get('coursePlayUrl'), ensure_ascii=False)[:900])
    print()
