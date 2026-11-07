# -*- coding: utf-8 -*-
"""并行分片下载器 —— 兴趣岛课程导出（API 模式）

为什么需要这个模块
------------------
实测数据（2026-11-07）：
  - ffmpeg 直接拉 m3u8（串行）：**0.83 MB/s**
  - 多线程拉分片（16~32 并发）：**8.4 MB/s**（CDN 侧硬顶，再高不涨）
  - Z 盘（SMB 网络盘）写入：**10.4 MB/s**
→ 瓶颈在 CDN，所以「多线程分片下载」能把总耗时从 ~33 小时压到 ~5 小时。

设计
----
  下载线程（课程级并发 N）→ 本地 D 盘临时目录存 .ts 分片（原子写入，可断点续传）
  转封装线程（1 个）      → 按序 cat 分片 → ffmpeg -c copy → 直接写 Z 盘
两条流水线重叠，总耗时 ≈ max(下载时间, 写盘时间)，而不是两者相加。

复用 xqd_app 已验证的规则（不要重新探测）：
  - master 清单按**短边** min(w,h) 选最清晰（这批课多竖屏）
  - DRM 清单要找同目录明文孪生，且**必须校验总时长**（否则会下错视频）
  - ffmpeg 临时输出必须以 .mp4 结尾，否则 muxer 初始化失败
"""
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import ssl
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import xqd_app as A          # noqa: E402
import xqd_api as API        # noqa: E402

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
     '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'


# ──────────────────────────────────────────────────────────
# 基础网络
# ──────────────────────────────────────────────────────────
def fetch(url, timeout=30, referer=None):
    """GET -> (status, body)。失败返回 (None, err)。"""
    h = {'User-Agent': UA, 'Accept': '*/*'}
    if referer:
        h['Referer'] = referer
    req = urllib.request.Request(url, headers=h)
    try:
        r = OP.open(req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b''
    except Exception:
        return None, b''


def short_side(res):
    m = re.match(r'(\d+)x(\d+)', res or '')
    return min(int(m.group(1)), int(m.group(2))) if m else 0


def pick_variant(text, directory, query):
    """master 清单 → [(res, url)]，按短边升序。

    与 xqd_app._pick_variant 同源，但这里额外把 master 的 query 继承给子清单
    （sign 绑定目录，不绑定文件名，所以可直接复用）。
    """
    out = []
    lines = [l.strip() for l in text.splitlines()]
    for i, l in enumerate(lines):
        if not l.startswith('#EXT-X-STREAM-INF'):
            continue
        m = re.search(r'RESOLUTION=(\d+)x(\d+)', l)
        res = m.group(0).split('=', 1)[1] if m else ''
        for j in range(i + 1, min(i + 4, len(lines))):
            if lines[j] and not lines[j].startswith('#'):
                u = lines[j]
                if not u.startswith('http'):
                    u = directory + u
                out.append((res, u))
                break
    out.sort(key=lambda v: short_side(v[0]))
    return out


def quality_filter(variants):
    """按 XQD_QUALITY 选一路。默认 max（短边最大）。"""
    if not variants:
        return None
    q = (os.environ.get('XQD_QUALITY') or 'max').strip().lower()
    if q == 'max':
        return variants[-1]
    try:
        want = int(q)
    except ValueError:
        want = 720
    for res, u in variants:
        if short_side(res) >= want:
            return (res, u)
    return variants[-1]


# ──────────────────────────────────────────────────────────
# 清单 → 分片列表
# ──────────────────────────────────────────────────────────
def manifest_segments(url, timeout=30):
    """沿用已验证规则把任意清单解析成 [(分片URL, 时长)]。

    返回 (segments, kind, note, total_seconds)
      kind: 'media' | 'drm' | 'master' | 'direct'
    """
    code, body = fetch(url, timeout=timeout)
    if code != 200:
        return None, None, '清单拉取失败 (HTTP %s)' % code, 0
    if not body.startswith(b'#EXTM3U'):
        # 直链媒体（AUDIO 类课程实测是 .MP3，如《清静经》领读音频）
        return [(url, 0.0)], 'direct', '直链媒体', 0
    text = body.decode('utf-8', 'replace')
    directory = url.rsplit('/', 1)[0] + '/'

    # ── master：选一路子清单 ──
    if 'EXT-X-STREAM-INF' in text:
        variants = pick_variant(text, directory, '')
        pick = quality_filter(variants)
        if not pick:
            return None, 'master', 'master 清单没有可用码率', 0
        res, sub = pick
        # 子清单继承 master 的 query（sign 绑目录）
        if '?' in url and '?' not in sub:
            sub = sub + '?' + url.split('?', 1)[1]
        c2, b2 = fetch(sub, timeout=timeout)
        if c2 != 200 or not b2.startswith(b'#EXTM3U'):
            return None, 'master', '子清单拉取失败 (HTTP %s)' % c2, 0
        t2 = b2.decode('utf-8', 'replace')
        base = sub.rsplit('/', 1)[0] + '/'
        segs = _parse_media(t2, base)
        return segs, 'master', '多码率 %s' % res, A._extinf_total(t2)

    # ── DRM：找同目录明文孪生（必须时长一致）──
    if 'EXT-X-KEY' in text:
        twin = A.find_plain_twin(text, url)
        if not twin:
            return None, 'drm', '未找到同源明文孪生，无法导出', 0
        c2, b2 = fetch(twin, timeout=timeout)
        if c2 != 200 or not b2.startswith(b'#EXTM3U'):
            return None, 'drm', '明文孪生拉取失败 (HTTP %s)' % c2, 0
        t2 = b2.decode('utf-8', 'replace')
        base = twin.rsplit('/', 1)[0] + '/'
        segs = _parse_media(t2, base)
        return segs, 'drm', '明文孪生', A._extinf_total(t2)

    # ── media：明文直连 ──
    segs = _parse_media(text, directory)
    return segs, 'media', '明文直连', A._extinf_total(text)


def _parse_media(text, base):
    """媒体清单 → [(分片URL, EXTINF时长)]，保持顺序。"""
    out = []
    dur = 0.0
    for raw in text.splitlines():
        l = raw.strip()
        if not l:
            continue
        if l.startswith('#EXTINF:'):
            try:
                dur = float(l.split(':', 1)[1].split(',')[0])
            except ValueError:
                dur = 0.0
            continue
        if l.startswith('#'):
            continue
        out.append((l if l.startswith('http') else base + l, dur))
        dur = 0.0
    return out


# ──────────────────────────────────────────────────────────
# 分片下载（并行 + 断点续传）
# ──────────────────────────────────────────────────────────
class SegFetcher(object):
    """把一节课的分片并行拉到本地目录。"""

    def __init__(self, workers=10, retries=3):
        self.workers = workers
        self.retries = retries
        self.lock = threading.Lock()
        self.done_bytes = 0
        self.failed = []

    def _one(self, url, path):
        # 断点续传：完整分片已存在就跳过
        if os.path.exists(path) and os.path.getsize(path) > 1024:
            with self.lock:
                self.done_bytes += os.path.getsize(path)
            return True
        tmp = path + '.part'
        for attempt in range(self.retries):
            try:
                code, body = fetch(url, timeout=40)
                if code == 200 and body:
                    with open(tmp, 'wb') as f:
                        f.write(body)
                    os.replace(tmp, path)
                    with self.lock:
                        self.done_bytes += len(body)
                    return True
            except Exception:
                pass
            time.sleep(0.6 * (attempt + 1))
        self.failed.append(url)
        return False

    def fetch_all(self, segments, out_dir, progress=None):
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        jobs = []
        for i, (u, _d) in enumerate(segments):
            path = os.path.join(out_dir, '%06d.ts' % i)
            jobs.append((u, path))
        ok = True
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futs = [ex.submit(self._one, u, p) for u, p in jobs]
            n = 0
            for f in futs:
                if not f.result():
                    ok = False
                n += 1
                if progress and n % 20 == 0:
                    progress(n, len(jobs))
        return ok, len(jobs)


# ──────────────────────────────────────────────────────────
# 转封装（cat 分片 → ffmpeg copy → 输出到 Z 盘）
# ──────────────────────────────────────────────────────────
def mux(seg_dir, out_path, nsegs, timeout=7200):
    """按序拼接分片并用 ffmpeg 重封装成 mp4。

    返回 (ok, note)
    """
    cat_path = os.path.join(seg_dir, '_joined.ts')
    with open(cat_path, 'wb') as out:
        for i in range(nsegs):
            p = os.path.join(seg_dir, '%06d.ts' % i)
            with open(p, 'rb') as f:
                shutil.copyfileobj(f, out, 1024 * 1024)

    tmp_out = A._ff_out_path(out_path)
    cmd = [A.ffmpeg_path(), '-y', '-loglevel', 'error',
           '-i', cat_path,
           '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
           '-movflags', '+faststart', tmp_out]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE)
    except FileNotFoundError:
        return False, '找不到 ffmpeg'
    try:
        _, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        return False, 'ffmpeg 超时'
    ok = p.returncode == 0 and os.path.exists(tmp_out) \
        and os.path.getsize(tmp_out) > 100000
    if ok:
        # 用 os.replace 覆盖（Windows 上 os.replace 本身就能覆盖已存在文件）。
        # 不用 os.remove —— 安全删除钩子会把不存在的文件当成错误抛出来。
        os.replace(tmp_out, out_path)
        return True, '%.1f MB' % (os.path.getsize(out_path) / 1048576)
    msg = err.decode('utf-8', 'replace')[-300:] if err else 'rc=%s' % p.returncode
    if os.path.exists(tmp_out):
        try:
            os.remove(tmp_out)
        except OSError:
            pass
    return False, msg


def download_direct(url, out_path, timeout=3600):
    """直链媒体（AUDIO 类的 MP3）→ 转封装成 mp4。

    先下到**本地唯一临时文件**，再 ffmpeg 转 mp4（AAC）。

    注意（实测踩过的坑）：临时文件**不能**放在营目录下的固定文件名 ——
    多线程同时下载同一营的不同课时��会互相覆盖同一个 raw.bin，
    导致转封装时读到被截断的文件（实测 1064s 的音频只存进 31.4s）。
    """
    import tempfile
    fd, raw = tempfile.mkstemp(prefix='xqd_direct_', suffix='.bin')
    os.close(fd)
    try:
        code, body = fetch(url, timeout=180)
        if code != 200 or not body:
            return False, '直链下载失败 (HTTP %s)' % code
        with open(raw, 'wb') as f:
            f.write(body)
        tmp_out = A._ff_out_path(out_path)
        cmd = [A.ffmpeg_path(), '-y', '-loglevel', 'error', '-i', raw,
               '-vn', '-c:a', 'aac', '-b:a', '128k',
               '-movflags', '+faststart', tmp_out]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE)
            _, err = p.communicate(timeout=timeout)
        except Exception as e:
            return False, 'ffmpeg 失败: %s' % e
        ok = p.returncode == 0 and os.path.exists(tmp_out) \
            and os.path.getsize(tmp_out) > 10000
        if ok:
            os.replace(tmp_out, out_path)
            return True, '%.1f MB' % (os.path.getsize(out_path) / 1048576)
        msg = err.decode('utf-8', 'replace')[-300:] if err \
            else 'rc=%s' % p.returncode
        return False, msg
    finally:
        try:
            os.remove(raw)
        except OSError:
            pass


def ffprobe_path():
    """ffprobe 可执行文件路径。

    注意：不能简单地把 ffmpeg 路径里的 'ffmpeg' 全部替换掉 ——
    安装目录名本身常含 'ffmpeg'（如 ffmpeg-8.0.1-essentials_build），
    全局替换会得到不存在的路径。只替换**文件名部分**。
    """
    p = A.ffmpeg_path()
    d, base = os.path.split(p)
    base = re.sub(r'^ffmpeg(\.exe)?$', 'ffprobe', base, flags=re.I)
    if not base.lower().startswith('ffprobe'):
        base = 'ffprobe.exe'
    cand = os.path.join(d, base)
    if os.path.exists(cand):
        return cand
    w = shutil.which('ffprobe')
    return w or 'ffprobe'


def probe_duration(path):
    """ffprobe 取时长（秒）。"""
    try:
        out = subprocess.check_output(
            [ffprobe_path(), '-v', 'error',
             '-show_entries', 'format=duration', '-of',
             'csv=p=0', path], stderr=subprocess.DEVNULL, timeout=120)
        return float(out.decode().strip())
    except Exception:
        return 0.0
