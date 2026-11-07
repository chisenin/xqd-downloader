# -*- coding: utf-8 -*-
"""测 sqs 域 + 带 appid 的 playListOfCourse。"""
import ssl, urllib.request, urllib.error, json
CTX=ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=CTX))
COOKIE=('rsessionId=<RSESSION_ID>; '
        'uid=<UID>; '
        'userId=<USER_ID>; caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')
def call(host, path, method='GET', body=None, extra=None, referer=None):
    h={'User-Agent':'Mozilla/5.0 (Linux; Android 12; M2102K1C) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
       'Cookie':COOKIE,'Accept':'application/json, text/plain, */*',
       'Referer': referer or ('https://%s/financial/training-intro'%host),
       'Origin':'https://%s'%host}
    if extra: h.update(extra)
    data=None
    if body is not None:
        h['Content-Type']='application/json;charset=UTF-8'; data=json.dumps(body).encode()
    req=urllib.request.Request('https://%s%s'%(host,path),data=data,headers=h,method=method)
    try:
        r=OP.open(req,timeout=20); return r.status,r.read()
    except urllib.error.HTTPError as e: return e.code,e.read()
    except Exception as e: return None,str(e).encode()

TESTS = [
 ('m.qianliao.net','/financial/api/gate/course/getCampCourseDetail','GET',None),
 ('m.qianliao.net','/financial/api/gate/course/getCoursePlayUrl','GET',None),
 ('m.qianliao.net','/financial/api/gate/course/playListOfCourse','GET',None),
 ('sqs.qianliao.net','/gate/sqs/campCourseData','GET',None),
 ('sqs.qianliao.net','/gate/sqs/openCourseData','GET',None),
 ('m.qianliao.net','/financial/api/gate/course/getSimpleCampDetail','GET',None),
]
for host,path,method,body in TESTS:
    st,b = call(host,path,method,body)
    t = b.decode('utf-8','replace').replace('\n',' ')
    kind = 'JSON' if t[:1] in '{[' else ('HTML' if t.lstrip()[:1]=='<' else '?')
    print('%-18s %-46s -> %-4s %-5s %s' % (host, path.replace('/financial/api',''), st, kind, t[:150]))
    print()
