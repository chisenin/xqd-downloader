# -*- coding: utf-8 -*-
"""兴趣岛 API 适配器 —— 用 Cookie 直连业务网关，无需模拟器、无需 GUI 登录器。

本模块是自建通用下载内核的「兴趣岛适配器」实现，
所有接口形态均来自官方前端 bundle（明文），已实测 code=0。

契约速查
--------
网关（转发模式）:
    POST https://m.qianliao.net/financial/api/transfer/gate/<endpoint>
    Body: {"transferData": {...}}
    Header: Content-Type: application/json;charset=UTF-8
    成功码在 **state.code**（不是顶层 code！）

端点:
    /gate/course/myCourseList                 营列表（开放课）
    /gate/course/myCourseListV2                营列表 V2（含 campName / courseTotalNum）
    /gate/course/playListOfCourse              课程表  body: {campId, onlyCourseCatalogue}
    /gate/course/getSimpleCampDetail           营详情  body: {campId}
    /gate/course/getCoursePlayUrl              播放地址 body: {videoHost, roomId, topicId,
                                                              businessId, businessType}
                                               businessType: 'camp' | 'OPEN_COURSE'

播放地址返回 data.coursePlayUrl:
    {type, playUrl, fileId, keySign, totalSeconds, coverUrl, appId, intelligentPlayUrl}
    playUrl 形如 https://video2.qianliao.net/<appId>/<8hex><bizFileId>/v.f1440283.m3u8?t=..&us=..&sign=..
    与既有 DRM 孪生规则一致（见 docs/01-已验证事实.md 第六、七节）。
"""
import ssl
import urllib.request
import urllib.error
import json
import re
import os
import time

DEFAULT_HOST = 'm.qianliao.net'
DEFAULT_COOKIE = (
    'rsessionId=<RSESSION_ID>'
    '<RSESSION_ID_TAIL>; '
    'userId=<USER_ID>; cUserId=<C_USER_ID>; '
    'uid=<UID>; '
    'caller=app_edu; platform=android; ver=4260; deviceType=phone; os=35'
)
UA_APP = 'Mozilla/5.0 (Linux; Android 12; M2102K1C) okhttp/4.9.0'


class QldError(Exception):
    pass


class QldClient:
    """兴趣岛业务 API 客户端。"""

    def __init__(self, cookie=None, host=DEFAULT_HOST, timeout=25, verbose=False):
        self.cookie = cookie or os.environ.get('QLD_COOKIE') or DEFAULT_COOKIE
        self.host = host
        self.timeout = timeout
        self.verbose = verbose
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        # ProxyHandler({}) => 禁用系统代理（实测必需，代理会吞掉 API 请求）
        self.op = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ctx))

    # ---------- 底层 ----------

    def _headers(self, referer=None):
        h = {'User-Agent': UA_APP,
             'Cookie': self.cookie,
             'Accept': 'application/json, text/plain, */*',
             'Origin': 'https://%s' % self.host,
             'Referer': referer or ('https://%s/' % self.host),
             'Content-Type': 'application/json;charset=UTF-8'}
        return h

    def api(self, endpoint, transfer_data=None, referer=None, retry=2):
        """POST /financial/api/transfer/gate/<endpoint>，返回 data 部分。"""
        url = 'https://%s/financial/api/transfer%s' % (self.host, endpoint)
        body = json.dumps({'transferData': transfer_data or {}}).encode()
        last = None
        for attempt in range(retry + 1):
            req = urllib.request.Request(url, data=body,
                                         headers=self._headers(referer), method='POST')
            try:
                r = self.op.open(req, timeout=self.timeout)
                raw = r.read().decode('utf-8', 'replace')
                js = json.loads(raw)
            except urllib.error.HTTPError as e:
                last = 'HTTP %s: %s' % (e.code, e.read()[:200])
                time.sleep(1.0)
                continue
            except Exception as e:
                last = str(e)[:200]
                time.sleep(1.0)
                continue
            state = js.get('state') or {}
            code = state.get('code')
            if code == 0:
                if self.verbose:
                    print('[qld] %s ok' % endpoint)
                return js.get('data')
            last = 'code=%s msg=%s' % (code, state.get('msg'))
            if code == 110:
                # 未登录 —— 重试无用
                break
            time.sleep(0.8)
        raise QldError('%s 失败: %s' % (endpoint, last))

    def fetch(self, url, referer=None, timeout=None):
        """GET 任意资源（清单、ts 等）。返回 (status, bytes)。"""
        h = {'User-Agent': UA_APP, 'Cookie': self.cookie, 'Accept': '*/*'}
        if referer:
            h['Referer'] = referer
        req = urllib.request.Request(url, headers=h)
        try:
            r = self.op.open(req, timeout=timeout or self.timeout)
            return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()[:300]
        except Exception as e:
            return None, str(e)[:200].encode()

    # ---------- 业务 ----------

    def my_courses(self):
        """营列表。返回 [{name, coverUrl, startTime, periodId, ...}]"""
        data = self.api('/gate/course/myCourseList', {'page': {'page': 1, 'size': 100}})
        return (data or {}).get('courses', [])

    def my_courses_v2(self):
        """营列表 V2（信息更全：campName / courseTotalNum / campStatus）。"""
        data = self.api('/gate/course/myCourseListV2', {'clientType': 'app'})
        return (data or {}).get('courses', [])

    def camp_detail(self, camp_id):
        return self.api('/gate/course/getSimpleCampDetail', {'campId': str(camp_id)})

    def playlist(self, camp_id):
        """整营课程表。返回 [{name, topicId, type, duration, roomId, playUrl, ...}]"""
        data = self.api('/gate/course/playListOfCourse',
                        {'campId': str(camp_id), 'onlyCourseCatalogue': True})
        return (data or {}).get('courses', [])

    def play_url(self, topic_id, business_id, business_type='camp',
                 room_id=None, video_host=None):
        """取播放地址。返回 data.coursePlayUrl 字典。"""
        td = {'videoHost': video_host,
              'roomId': room_id,
              'topicId': topic_id,
              'businessId': '' if business_type == 'OPEN_COURSE' else str(business_id),
              'businessType': business_type}
        data = self.api('/gate/course/getCoursePlayUrl', td)
        return (data or {}).get('coursePlayUrl') or {}

    def play_url_for_course(self, course, camp_id):
        """按课程表条目取播放地址（自动选业务类型）。"""
        btype = 'camp'
        bid = str(camp_id)
        if course.get('roomId') and not course.get('topicId'):
            btype = 'OPEN_COURSE'
        return self.play_url(course.get('topicId'), bid, btype,
                              room_id=course.get('roomId'))


# ---------- 清单解析工具（与 docs/01-已验证事实.md 第七节一致） ----------

def parse_master(text):
    """解析 master 清单 -> [(url, short_edge, w, h)]。竖屏课按短边选清晰度。"""
    out = []
    lines = [l.strip() for l in text.splitlines()]
    for i, l in enumerate(lines):
        if not l.startswith('#EXT-X-STREAM-INF'):
            continue
        m = re.search(r'RESOLUTION=(\d+)x(\d+)', l)
        if not m:
            continue
        w, h = int(m.group(1)), int(m.group(2))
        for j in range(i + 1, min(i + 4, len(lines))):
            if lines[j] and not lines[j].startswith('#'):
                out.append((lines[j], min(w, h), w, h))
                break
    return out


def total_seconds(text):
    return sum(float(x) for x in re.findall(r'#EXTINF:\s*([\d.]+)', text))


def classify(text):
    """清单类型：drm / master / media。"""
    if 'EXT-X-KEY' in text:
        return 'drm'
    if 'EXT-X-STREAM-INF' in text:
        return 'master'
    return 'media'


def url_dir(url):
    """host/appId/<8hex><bizFileId>  -> 目录部分（不含文件与 query）"""
    p = url.split('://', 1)[1] if '://' in url else url
    return '/'.join(p.split('/')[:-1])


def sibling(url, newname):
    """同目录换文件名，保留原 query（sign 只绑定目录与 t，可复用）。"""
    q = ('?' + url.split('?', 1)[1]) if '?' in url else ''
    return 'https://%s/%s%s' % (url_dir(url), newname, q)


def strip_encdomain(url):
    """请求明文孪生模板时必须去掉 encdomain=cmv1，否则 403。"""
    return re.sub(r'[?&]encdomain=cmv1', '', url)


def pick_plain_twin(url, want_seconds, client):
    """DRM 清单 -> 明文孪生。必须做时长校验，否则会下错视频。"""
    m = re.search(r'video_(\d+)_', url) or re.search(r'v\.f(\d+)\.m3u8', url)
    if not m:
        return None, '无法从 URL 推断孪生编号'
    twin = strip_encdomain(sibling(url, 'v.f%s.m3u8' % m.group(1)))
    st, body = client.fetch(twin)
    if st != 200:
        return None, '孪生拉取失败 HTTP %s' % st
    text = body.decode('utf-8', 'replace')
    got = total_seconds(text)
    tol = max(1.0, (want_seconds or 0) * 0.005)
    if want_seconds and abs(got - want_seconds) > tol:
        return None, '孪生时长 %.1fs 与目标 %.1fs 不符' % (got, want_seconds)
    return twin, '孪生可用（时长 %.1fs）' % got


if __name__ == '__main__':
    import sys
    c = QldClient(verbose=True)
    camps = c.my_courses_v2()
    print('营数: %d' % len(camps))
    for x in camps[:8]:
        print('  %-28s total=%-4s status=%-8s periodId=%s'
              % (x.get('campName'), x.get('courseTotalNum'),
                 x.get('campStatus'), x.get('periodId')))
    if len(sys.argv) > 1:
        cid = sys.argv[1]
        pl = c.playlist(cid)
        print('课程数: %d' % len(pl))
        for x in pl[:5]:
            print('  %-40s %s %s' % (x.get('name'), x.get('type'), x.get('duration')))
