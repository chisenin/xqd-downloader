# -*- coding: utf-8 -*-
"""平台适配层 —— 扩展接口。

将来接新平台（网易163、超星、智慧树…）时，只需实现一个 ``Platform`` 子类
并注册到 ``REGISTRY``，GUI 侧不用改任何代码。

子类需要提供
------------
platform_id    : str   平台标识（用于命令行 --platform）
display_name   : str   GUI 上显示的名字
camp_kind      : str   营的类型名（正式营 / 体验营 …）
list_camps(kind)-> [Camp]
camp_catalog(camp)-> [Lesson]
resolve(camp, lesson)-> str   播放地址
"""

import datetime
import os
import re
import ssl
import urllib.error
import urllib.request

UA_APP = 'okhttp/4.9.0'
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=_CTX))


class Camp(object):
    """一个营（课程集合）。"""

    def __init__(self, name, camp_id, kind='', count=0, badge=''):
        self.name = name
        self.camp_id = camp_id
        self.kind = kind
        self.count = count
        self.badge = badge

    def __repr__(self):
        return '<Camp %s (%s节)>' % (self.name, self.count)


class Lesson(object):
    """一节课。"""

    def __init__(self, index, title, when='', duration=0, ltype='',
                 topic_id='', room_id='', camp=''):
        self.index = index
        self.title = title
        self.when = when
        self.duration = duration or 0
        self.type = ltype
        self.topic_id = topic_id
        self.room_id = room_id
        self.camp = camp
        self.when_date = ''       # YYYY.MM.DD
        # 运行期状态
        self.progress = 0        # 0~100
        self.state = 'idle'       # idle|queued|running|done|failed|skipped
        self.message = ''
        self.out_path = ''

    @property
    def key(self):
        return (self.camp, self.index)

    @property
    def display(self):
        return '[%02d] %s' % (self.index + 1, self.title)

    def __repr__(self):
        return '<Lesson %s %s>' % (self.index, self.title)


# ── 文件名规范 ───────────────────────────────────────────────

_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')
_RESERVED = {'CON', 'PRN', 'AUX', 'NUL',
             'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7',
             'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5',
             'LPT6', 'LPT7', 'LPT8', 'LPT9'}


def safe_name(name):
    """文件名清洗。

    只替换 Windows ASCII 非法字符；**全角冒号「：」必须保留**
    （用户要求的命名格式，Windows 与 ffmpeg 都安全）。
    """
    if not name:
        return '未命名'
    s = _ILLEGAL.sub('_', str(name)).strip().rstrip('.')
    if s.upper() in _RESERVED:
        s = '_' + s
    return s or '未命名'


def _fmt_date(ms):
    """startTime 毫秒 -> 'YYYY.MM.DD'。"""
    if not ms:
        return ''
    try:
        return datetime.datetime.fromtimestamp(ms / 1000.0).strftime('%Y.%m.%d')
    except Exception:
        return ''


def _fmt_when(ms):
    """startTime 毫秒 -> 'MM.DD HH:MM'（与 App 课程卡片一致的显示格式）。"""
    if not ms:
        return ''
    try:
        return datetime.datetime.fromtimestamp(ms / 1000.0).strftime('%m.%d %H:%M')
    except Exception:
        return ''


def lesson_stem(lesson):
    """成品文件**主名**（不含扩展名）：<序号>.<课名>.<日期>

    主名是「同一节课」的唯一标识，与成品用哪种容器无关。
    已下载检测靠它匹配（音频可能是 .mp3 也可能是 .m4a）。
    """
    idx = (lesson.index or 0) + 1
    parts = ['%d.%s' % (idx, safe_name(lesson.title))]
    date = lesson.when_date or ''
    if date:
        parts.append(date)
    return '.'.join(parts)


def expected_ext(lesson):
    """按课程类型决定成品扩展名。

    实测（2026-11-07，266 节课表）：
      * VIDEO / INTELLIGENT_LIVE 原始是 HLS(m3u8) 分片 → 统一转封装 MP4
      * AUDIO 原始**本身就是音频文件**（.mp3 / .m4a），不该塞进 MP4 容器
        → 保持原始格式
    """
    if (lesson.type or '').upper() == 'AUDIO':
        return '.mp3'
    return '.mp4'


def course_filename(lesson, used=None, ext=None):
    """成品文件名：<序号>.<课名>.<日期>.<扩展名>

    序号 = 营内课表顺序（1 起），与 App 课程列表顺序一致。

    ⚠️ 不再产生 ``-1`` / ``-2`` 重名后缀。
    原因：序号参与主键，营内本就唯一；加后缀只会制造「同一节课两个文件」
    的混乱（旧批处理留下的 ``xxx.mp4`` 与 ``xxx-1.mp4`` 就是这么来的）。
    重名时的正确处理是：
      * 已有完整成品 → 跳过下载
      * 已有残缺文件 → 删掉，用规范名覆盖重下
    （见 xqd_dedupe.check_group / purge_broken）

    used 参数保留仅为兼容旧调用，忽略之。
    """
    base = lesson_stem(lesson)
    ext = ext or expected_ext(lesson)
    return base + ext


# ── 平台基类 ─────────────────────────────────────────────────

class Platform(object):
    """平台适配器基类。"""

    platform_id = 'base'
    display_name = '未命名平台'
    camp_kinds = ('正式营',)

    def __init__(self, cookie=''):
        self.cookie = cookie
        self._camps = {}

    # —— 必须实现 ——
    def list_camps(self, kind):
        raise NotImplementedError

    def camp_catalog(self, camp):
        raise NotImplementedError

    def resolve(self, camp, lesson):
        raise NotImplementedError

    # —— 可选 ——
    def check_auth(self):
        """检查授权是否可用。返回 (ok, message)。"""
        return bool(self.cookie), '未设置 Cookie'

    def close(self):
        pass


# ── 兴趣岛实现 ───────────────────────────────────────────────

class QianliaoPlatform(Platform):
    """兴趣岛（qianliao）。

    业务网关契约（已在 docs/09-兴趣岛业务API.md 记录）::

        POST https://m.qianliao.net/financial/api/transfer/gate/<endpoint>
        Body: {"transferData": {...}}
        成功码在 state.code（不是顶层 code）
    """

    platform_id = 'qianliao'
    display_name = '兴趣岛'
    camp_kinds = ('正式营', '体验营')

    HOST = 'm.qianliao.net'
    GATEWAY = 'https://%s/financial/api/transfer' % HOST

    # skyType 参数把营分类隔开
    SKY_TYPES = {'正式营': 'FINANCIAL', '体验营': 'INTENTION'}

    def __init__(self, cookie=''):
        Platform.__init__(self, cookie)
        self._catalogs = {}
        self._camp_cache = {}

    # —— HTTP ——
    def _api(self, endpoint, transfer_data=None, timeout=30):
        """调业务网关。返回解析后的 data（失败返回 None）。"""
        import json
        headers = {
            'User-Agent': UA_APP,
            'Cookie': self.cookie,
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://%s' % self.HOST,
            'Referer': 'https://%s/' % self.HOST,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        body = json.dumps({'transferData': transfer_data or {}}).encode('utf-8')
        req = urllib.request.Request(self.GATEWAY + endpoint, data=body,
                                     headers=headers, method='POST')
        try:
            r = _OPENER.open(req, timeout=timeout)
            raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
        except Exception as e:
            raise IOError('请求失败：%s' % e)

        # 失败时网关返回 HTML 而非 JSON，200 不等于成功
        if not raw.startswith(b'{'):
            raise IOError('网关返回非 JSON（可能未授权或被代理拦截）')
        obj = json.loads(raw.decode('utf-8', 'replace'))
        state = obj.get('state') or {}
        if state.get('code') != 0:
            raise IOError('接口报错：%s' % (state.get('msg') or '未知错误'))
        return obj.get('data') or {}

    # —— 授权 ——
    def check_auth(self):
        if not self.cookie:
            return False, '尚未获取授权'
        try:
            self._api('/gate/course/myCourseListV2',
                      {'skyType': 'FINANCIAL', 'page': {'page': 1, 'size': 1}},
                      timeout=20)
            return True, '授权有效'
        except Exception as e:
            return False, '授权无效：%s' % e

    # —— 营 ——
    def list_camps(self, kind='正式营'):
        sky = self.SKY_TYPES.get(kind)
        td = {'page': {'page': 1, 'size': 200}}
        if sky:
            td['skyType'] = sky
        data = self._api('/gate/course/myCourseListV2', td)
        camps = []
        for c in data.get('courses') or []:
            camps.append(Camp(
                name=c.get('campName') or '',
                camp_id=str(c.get('campId') or ''),
                kind=kind,
                count=int(c.get('courseTotalNum') or 0),
                badge='%s节' % (c.get('courseTotalNum') or 0)))
        self._camp_cache = {}
        return camps

    def _find_camp(self, camp):
        """按名字找到 Camp 对象（含 campId）。"""
        if isinstance(camp, Camp):
            return camp
        for kind in self.camp_kinds:
            try:
                lst = self.list_camps(kind)
            except Exception:
                continue
            for c in lst:
                if c.name == camp:
                    return c
        # 兜底：只按名字构造，campId 从课表接口反查
        return None

    # —— 课表 ——
    def camp_catalog(self, camp):
        name = camp.name if isinstance(camp, Camp) else str(camp)
        if name in self._catalogs:
            return self._catalogs[name]

        camp_obj = self._find_camp(camp)
        camp_id = camp_obj.camp_id if camp_obj else None
        if not camp_id:
            # 用轻课列表反查 campId
            data = self._api('/gate/course/myCourseListV2',
                             {'page': {'page': 1, 'size': 200}})
            for c in data.get('courses') or []:
                if c.get('campName') == name:
                    camp_id = str(c.get('campId'))
                    break
        if not camp_id:
            raise IOError('找不到营：%s' % name)

        data = self._api('/gate/course/playListOfCourse',
                         {'campId': camp_id, 'onlyCourseCatalogue': True})
        raw = data.get('courses') or []

        lessons = []
        for i, c in enumerate(raw):
            le = Lesson(
                index=i,
                title=c.get('name') or '',
                when=_fmt_when(c.get('startTime')),
                duration=int(c.get('duration') or 0),
                ltype=c.get('type') or '',
                topic_id=c.get('topicId') or '',
                room_id=c.get('roomId') or '',
                camp=name)
            le.when_date = _fmt_date(c.get('startTime'))
            lessons.append(le)

        self._catalogs[name] = lessons
        return lessons

    # —— 播放地址 ——
    def resolve(self, camp, lesson):
        name = camp.name if isinstance(camp, Camp) else str(camp)
        camp_obj = self._find_camp(camp)
        camp_id = camp_obj.camp_id if camp_obj else ''
        if not camp_id:
            for c in self._api('/gate/course/myCourseListV2',
                                {'page': {'page': 1, 'size': 200}}).get('courses') or []:
                if c.get('campName') == name:
                    camp_id = str(c.get('campId'))
                    break

        business_type = 'OPEN_COURSE' if lesson.type == 'OPEN_COURSE' else 'camp'
        data = self._api('/gate/course/getCoursePlayUrl', {
            'videoHost': '',
            'roomId': lesson.room_id or '',
            'topicId': lesson.topic_id or '',
            'businessId': camp_id,
            'businessType': business_type,
        })

        # 网关返回的是一个对象，里面再套一层 playUrl / coursePlayUrl
        url = ''
        candidates = [data]
        for key in ('playUrl', 'coursePlayUrl', 'url'):
            if isinstance(data, dict) and isinstance(data.get(key), dict):
                candidates.append(data[key])
        for node in candidates:
            if not isinstance(node, dict):
                continue
            for key in ('playUrl', 'coursePlayUrl', 'url'):
                val = node.get(key)
                if isinstance(val, str) and val.startswith('http'):
                    url = val
                    break
            if url:
                break

        if not url:
            raise IOError('未取得播放地址：%s' % str(data)[:160])
        return url


# ── 注册表 ───────────────────────────────────────────────────

REGISTRY = {
    QianliaoPlatform.platform_id: QianliaoPlatform,
}


def create_platform(platform_id, cookie=''):
    """按 id 创建平台实例。"""
    cls = REGISTRY.get(platform_id)
    if not cls:
        raise KeyError('未知平台：%s（可用：%s）'
                       % (platform_id, ', '.join(REGISTRY)))
    return cls(cookie=cookie)
