"""兴趣岛业务网关 —— 对应 C# `Xqd.Core.Api.QianliaoClient` / `QianliaoPlatform`。

★ 三条踩过的坑，写进代码里当护栏：
  1. **必须禁用系统代理**：否则网关返回 HTML 登录页（urllib 默认会读环境代理）。
  2. **成功码在 state.code，不在顶层 code**；缺失即失败。
  3. **200 不等于成功**：响应首字节如果不是 '{'，直接判「非 JSON」，别硬解析。

这一层只负责「拿到数据」，下载编排不在这里——正式版由 C# 引擎做。
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.request
from urllib.parse import urlencode

from .config import load_cookie

HOST = "m.qianliao.net"
UA = "okhttp/4.9.0"
URL_KEYS = ("playUrl", "coursePlayUrl", "url")
MAX_DEPTH = 8


class QldError(RuntimeError):
    pass


def _body(data: dict | None) -> bytes:
    return json.dumps({"transferData": data or {}}, ensure_ascii=False).encode("utf-8")


def _opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),               # ★ 禁用系统代理
        urllib.request.HTTPSHandler(context=ctx),
    )


class QldClient:
    def __init__(self, cookie: str | None = None, host: str = HOST):
        self.host = host or HOST
        self.cookie = cookie if cookie is not None else load_cookie()

    @property
    def gateway(self) -> str:
        return f"https://{self.host}/financial/api/transfer"

    def api(self, endpoint: str, transfer_data: dict | None = None,
            timeout: int = 30, retry: int = 2) -> dict:
        td = transfer_data or {}
        url = self.gateway + endpoint
        last = ""
        for attempt in range(retry + 1):
            req = urllib.request.Request(
                url, data=_body(td), method="POST",
                headers={
                    "Content-Type": "application/json; charset=UTF-8",
                    "User-Agent": UA,
                    "Accept": "application/json, text/plain, */*",
                    "Cookie": self.cookie or "",
                    "Origin": f"https://{self.host}",
                    "Referer": f"https://{self.host}/",
                })
            try:
                with _opener().open(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8", "replace")
            except Exception as exc:
                last = f"请求失败：{exc}"
                if attempt < retry:
                    time.sleep(0.8)
                    continue
                break

            head = raw.lstrip()
            if not head or head[0] != "{":
                first = head[0] if head else ""
                last = f"网关返回非 JSON（可能未授权或被代理拦截；首字节 {first!r}）"
                if attempt < retry:
                    time.sleep(0.8)
                    continue
                break

            try:
                root = json.loads(raw)
            except Exception as exc:
                last = f"JSON 解析失败：{exc}"
                if attempt < retry:
                    time.sleep(0.8)
                    continue
                break

            state = root.get("state") or {}
            code = _long(state.get("code"), -999)
            if code == 0:
                data = root.get("data")
                return data if isinstance(data, (dict, list)) else {}
            last = f"code={code} msg={state.get('msg', '')}"
            if code == 110:            # 未登录，重试无用
                break
            if attempt < retry:
                time.sleep(0.8)
        raise QldError(f"{endpoint} 失败：{last}")

    # ── 业务端点 ──

    def my_courses_v2(self, sky_type: str = "", page: int = 1, size: int = 200) -> dict:
        td: dict = {"page": {"page": page, "size": size}}
        if sky_type:
            td["skyType"] = sky_type
        return _as_dict(self.api("/gate/course/myCourseListV2", td))

    def play_list_of_course(self, camp_id: str) -> dict:
        return _as_dict(self.api("/gate/course/playListOfCourse",
                                 {"campId": camp_id, "onlyCourseCatalogue": True}))

    def open_course_play_list(self, period_id: str) -> dict:
        """公开课没有 campId，只能用它自己的端点。"""
        return _as_dict(self.api("/gate/openCourse/playListOfCourse",
                                 {"periodId": period_id}))

    def get_course_play_url(self, business_id: str, business_type: str,
                            topic_id: str, room_id: str, video_host: str = "") -> dict:
        return _as_dict(self.api("/gate/course/getCoursePlayUrl", {
            "videoHost": video_host,
            "roomId": room_id,
            "topicId": topic_id,
            "businessId": business_id,
            "businessType": business_type or "camp",
        }))


def find_play_url(data) -> str:
    """响应可能套多层：按 playUrl → coursePlayUrl → url 优先，再递归其余键兜底。"""
    return _find_http(data, 0)


def _find_http(node, depth: int) -> str:
    if depth > MAX_DEPTH:
        return ""
    if isinstance(node, str):
        return node if node.lower().startswith("http") else ""
    if isinstance(node, list):
        for item in node:
            got = _find_http(item, depth + 1)
            if got:
                return got
        return ""
    if isinstance(node, dict):
        for key in URL_KEYS:
            got = _find_http(node.get(key), depth + 1)
            if got:
                return got
        for key, val in node.items():
            if key.lower() in [k.lower() for k in URL_KEYS]:
                continue
            got = _find_http(val, depth + 1)
            if got:
                return got
    return ""


# ── 平台适配（营列表 / 课表 / 播放地址）──────────────────────────────

SKY_TYPES = {"正式营": "FINANCIAL", "体验营": "INTENTION"}


def camp_type_of(sku: str) -> str:
    if sku == "FINANCIAL":
        return "正式营"
    if sku in ("LAUNCH", "INTENTION"):
        return "体验营"
    return "公开课"


class Platform:
    """极简版：够验证「营 → 课表 → 播放地址」这条链路，不做并发与缓存。"""

    def __init__(self, cookie: str | None = None):
        self.client = QldClient(cookie)
        self._camps: dict[str, dict] = {}

    def list_camps(self, kind: str = "全部") -> list[dict]:
        if kind == "轻课":
            return []
        sky = SKY_TYPES.get(kind, "")
        data = self.client.my_courses_v2(sky)
        camps = []
        for c in data.get("courses", []) or []:
            camp = {
                "name": _str(c.get("campName")),
                "campId": _str(c.get("campId")),
                "periodId": _str(c.get("periodId")),
                "skuType": _str(c.get("skuType")),
                "businessType": _str(c.get("businessType")),
                "businessId": _str(c.get("businessId")),
                "count": _long(c.get("courseTotalNum")),
                "kind": kind if kind else camp_type_of(_str(c.get("skuType"))),
            }
            if kind == "公开课" and camp["skuType"] != "OPEN_COURSE":
                continue
            camps.append(camp)
            if camp["name"]:
                old = self._camps.get(camp["name"])
                # 同名时优先保留有 campId 的（付费营），避免公开课批次顶掉正课
                if old is None or not old.get("campId"):
                    self._camps[camp["name"]] = camp
        return camps

    def lookup(self, name: str) -> dict | None:
        if name in self._camps:
            return self._camps[name]
        for kind in ("正式营", "体验营", "全部"):
            self.list_camps(kind)
            if name in self._camps:
                return self._camps[name]
        return None

    def camp_catalog(self, camp) -> list[dict]:
        if isinstance(camp, str):
            camp = self.lookup(camp) or {"name": camp}
        camp_id = camp.get("campId") or ""
        period_id = camp.get("periodId") or ""
        if camp_id:
            data = self.client.play_list_of_course(camp_id)
        elif period_id:
            data = self.client.open_course_play_list(period_id)
        else:
            return []

        lessons = []
        for i, c in enumerate(data.get("courses", []) or []):
            start = _long(c.get("startTime"))
            from .naming import fmt_date, fmt_when
            lessons.append({
                "index": i,                       # 课表顺序 == App 顺序 == 成品序号
                "title": _str(c.get("name")),
                "when": fmt_when(start),
                "date": fmt_date(start),
                "duration": _dbl(c.get("duration")),
                "type": _str(c.get("type")),
                "topicId": _str(c.get("topicId")),
                "roomId": _str(c.get("roomId")),
                "fileId": _str(c.get("playUrl")),
            })
        return lessons

    def resolve(self, camp, lesson: dict) -> str:
        if isinstance(camp, str):
            camp = self.lookup(camp) or {"name": camp}
        camp_id = camp.get("campId") or ""
        if not camp_id:
            business_type, business_id = "OPEN_COURSE", camp.get("periodId") or ""
        else:
            open_course = (lesson.get("type") or "").upper() == "OPEN_COURSE"
            business_type = "OPEN_COURSE" if open_course else "camp"
            business_id = camp_id

        topic_id, room_id = lesson.get("topicId") or "", lesson.get("roomId") or ""
        if not topic_id and not room_id:
            raise QldError("缺少 topicId / roomId，无法解析播放地址")

        data = self.client.get_course_play_url(business_id, business_type, topic_id, room_id)
        url = find_play_url(data)
        if not url:
            raise QldError("未取得播放地址：getCoursePlayUrl 响应里找不到 http 播放地址")
        return url


# ── 网关字段容错（类型不固定：数字可能是字符串）────────────────────

def _str(v, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return str(v)


def _long(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        try:
            return int(float(str(v)))
        except Exception:
            return default


def _dbl(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _as_dict(v) -> dict:
    return v if isinstance(v, dict) else {}
