# -*- coding: utf-8 -*-
"""用正确的 qianliao.net 域 cookie 重试 API。"""
import ssl, urllib.request, urllib.error, json
CTX=ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=CTX))

COOKIE=('rsessionId=<RSESSION_ID>; '
        'uid=<UID>; '
        'userId=<USER_ID>; caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35')

def call(path, method='GET', body=None, host='m.qianliao.net', extra=None):
    h={'User-Agent':'Mozilla/5.0 (Linux; Android 12; M2102K1C) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
       'Cookie':COOKIE,'Accept':'application/json, text/plain, */*',
       'Referer':'https://%s/financial/training-intro'%host,'Origin':'https://%s'%host}
    if extra: h.update(extra)
    data=None
    if body is not None:
        h['Content-Type']='application/json;charset=UTF-8'; data=json.dumps(body).encode()
    req=urllib.request.Request('https://%s%s'%(host,path),data=data,headers=h,method=method)
    try:
        r=OP.open(req,timeout=20); return r.status,r.read()
    except urllib.error.HTTPError as e: return e.code,e.read()
    except Exception as e: return None,str(e).encode()

P='/financial/api/gate/course/myCourseListV2'
for method,body in (('GET',None),('POST',{'clientType':'app'}),('POST',{})):
    st,b=call(P,method,body)
    t=b.decode('utf-8','replace').replace('\n',' ')
    print('%-4s body=%-22s -> %s  %s' % (method, str(body)[:20], st, t[:260]))
    print()
