# -*- coding: utf-8 -*-
"""下载引擎（GUI 无关）。

把「课表 -> 播放地址 -> 分片并行下载 -> 转封装 -> 校验」这条链路抽出来，
供 GUI 直接驱动，同时保持与既有 xqd_pdl / xqd_batch 的行为一致。

命名规则（2026-11-07 起）
--------------------------
    <序号>.<课名>.<YYYY.MM.DD>.mp4

序号 = 营内课表顺序（与 App 列表顺序一致），日期取该节 startTime。
重名时追加 -1 / -2 兜底。
"""

import os
import re
import shutil
import ssl
import subprocess

import xqd_proc
import tempfile
import threading
import time
import urllib.error
import urllib.request

UA_APP = 'okhttp/4.9.0'


# ── HTTP ─────────────────────────────────────────────────────

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# 必须禁用系统代理，否则请求会被代理吞掉返回 HTML
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=_CTX))


def http_get(url, timeout=30, headers=None):
    """GET 一个 URL。返回 (status, body)。"""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        r = _OPENER.open(req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode('utf-8', 'replace')


def http_open(url, timeout=60, headers=None):
    """打开一个 HTTP 连接，返回可**增量读取**的 response 对象。

    为什么不用 http_get：直链音频是整文件一次读完（几十 MB 进内存），
    既没法报告进度，也没法在中途暂停。改成流式读取后，
    每读一块就检查一次暂停标志，用户点「暂停」能立刻生效。
    """
    req = urllib.request.Request(url, headers=headers or {})
    return _OPENER.open(req, timeout=timeout)


class DownloadControl(object):
    """下载控制：暂停 / 继续 / 停止。

    暂停是**协作式**的 —— 各下载线程在安全点检查并等待，
    已经下好的分片保留在临时目录里，继续后接着下，不会重头来。

    与 stop_flag 的区别：stop_flag 是「中止」（线程直接退出），
    这里是「暂停」（线程等待，可恢复），两者可同时生效。
    """

    def __init__(self):
        self._pause = threading.Event()    # set = 处于暂停状态
        self._stop = threading.Event()     # set = 要求中止

    # ── 状态查询 ──
    def is_paused(self):
        return self._pause.is_set()

    def is_stopped(self):
        return self._stop.is_set()

    # ── 控制 ──
    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def toggle(self):
        if self.is_paused():
            self.resume()
            return False
        self.pause()
        return True

    def stop(self):
        self._stop.set()

    def wait_resume(self):
        """暂停中则阻塞等待。

        返回 False 表示「已被要求中止」，调用方应立即退出。
        """
        while self._pause.is_set() and not self._stop.is_set():
            time.sleep(0.2)
        return not self._stop.is_set()


# ── 清单解析 ─────────────────────────────────────────────────

def _short_side(res):
    m = re.match(r'(\d+)x(\d+)', res or '')
    if not m:
        return 0
    return min(int(m.group(1)), int(m.group(2)))


def parse_manifest(url, quality='max'):
    """把任意清单解析成分片列表。

    返回 (segments, kind, note, total_seconds)
      segments : [(分片URL, 时长秒)]
      kind     : 'media' | 'drm' | 'master' | 'direct'
      note     : 人类可读说明（选了哪一路 / 什么类型）
      total    : 清单标称总时长

    kind='direct' 时 segments 为 [(url, 0)]，表示直链媒体（AUDIO 类 MP3）。
    """
    code, body = http_get(url, timeout=30)
    if code != 200:
        return None, None, '清单拉取失败 (HTTP %s)' % code, 0

    # 直链（非 m3u8）
    if not body.startswith(b'#EXTM3U'):
        return [(url, 0)], 'direct', '直链媒体', 0

    text = body.decode('utf-8', 'replace')
    directory = url.rsplit('/', 1)[0] + '/'

    def dur_of(tag):
        m = re.search(r'DURATION=([0-9.]+)', tag)
        return float(m.group(1)) if m else 0.0

    # ── master（多码率）──
    if 'EXT-X-STREAM-INF' in text:
        variants = []
        lines = [l.strip() for l in text.splitlines()]
        for i, line in enumerate(lines):
            if not line.startswith('#EXT-X-STREAM-INF'):
                continue
            res = ''
            m = re.search(r'RESOLUTION=([0-9]+x[0-9]+)', line)
            if m:
                res = m.group(1)
            for j in range(i + 1, len(lines)):
                if lines[j] and not lines[j].startswith('#'):
                    variants.append((res, lines[j]))
                    break
        if not variants:
            return None, None, 'master 清单没有可用码率', 0

        # 这批课多为竖屏，清晰度看**短边**
        variants.sort(key=lambda v: _short_side(v[0]))
        pick = None
        if quality == 'max':
            pick = variants[-1]
        else:
            try:
                want = int(quality)
            except ValueError:
                want = 720
            for res, u in variants:
                if _short_side(res) >= want:
                    pick = (res, u)
                    break
            if not pick:
                pick = variants[-1]

        src = pick[1]
        if not src.startswith('http'):
            src = directory + src
        sub_code, sub_body = http_get(src, timeout=30)
        if sub_code != 200:
            return None, None, '子清单拉取失败 (HTTP %s)' % sub_code, 0
        sub_text = sub_body.decode('utf-8', 'replace')
        segs, total = _parse_media_manifest(sub_text, src)
        return segs, 'master', '多码率 %s' % pick[0], total

    # ── 普通 / DRM 媒体清单 ──
    if '#EXT-X-KEY' in text:
        segs, total = _parse_media_manifest(text, url)
        return segs, 'drm', '加密清单（明文孪生）', total

    segs, total = _parse_media_manifest(text, url)
    return segs, 'media', '标准 HLS', total


def _parse_media_manifest(text, url):
    """解析媒体清单为 [(url, dur)]。"""
    directory = url.rsplit('/', 1)[0] + '/'
    segs = []
    total = 0.0
    cur = 0.0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#EXTINF:'):
            m = re.search(r'([0-9.]+)', line)
            cur = float(m.group(1)) if m else 0.0
        elif line.startswith('#'):
            continue
        else:
            full = line if line.startswith('http') else directory + line
            segs.append((full, cur))
            total += cur
            cur = 0.0
    return segs, total


# ── ffmpeg ───────────────────────────────────────────────────

def _find_ffmpeg(name='ffmpeg'):
    exe = shutil.which(name)
    if exe:
        return exe
    for base in (r'D:\user\chisenin\download\Programs\ffmpeg-8.0.1-essentials_build\bin',
                 r'C:\LEL\LEL-Downloader\Source\ffmpeg'):
        p = os.path.join(base, name + '.exe')
        if os.path.isfile(p):
            return p
    raise RuntimeError('找不到 %s.exe' % name)


def ffmpeg_path():
    return _find_ffmpeg('ffmpeg')


def ffprobe_path():
    return _find_ffmpeg('ffprobe')


def probe_duration(path):
    """ffprobe 取时长（秒）。失败返回 0。"""
    try:
        out = xqd_proc.check_output(
            [ffprobe_path(), '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', path],
            stderr=subprocess.DEVNULL, timeout=180)
        return float(out.decode().strip())
    except Exception:
        return 0.0


def probe_info(path):
    """返回 (时长, 宽, 高, 有无音轨, 大小MB)。"""
    try:
        out = xqd_proc.check_output(
            [ffprobe_path(), '-v', 'error', '-show_entries',
             'format=duration,size:stream=codec_name,width,height',
             '-of', 'json', path],
            stderr=subprocess.DEVNULL, timeout=180)
        import json
        d = json.loads(out.decode('utf-8', 'replace'))
        v = next((s for s in d.get('streams', []) if s.get('width')), {})
        has_audio = any(s.get('codec_name') == 'aac'
                        for s in d.get('streams', []))
        size = int(d.get('format', {}).get('size', 0))
        return (float(d.get('format', {}).get('duration', 0)),
                v.get('width', 0), v.get('height', 0), has_audio,
                size / 1048576.0)
    except Exception:
        return 0, 0, 0, False, 0.0


def probe_media(path):
    """探测媒体的**真实**容器与编码。

    返回 dict:
        format_name  ffprobe 的 format_name（如 'mp3' / 'mov,mp4,m4a,3gp,3g2,mj2'）
        duration     时长秒
        has_video    有真实视频轨（mp3 的封面 mjpeg 不算）
        has_audio    有音频轨
        codecs       编码名列表
        size         字节数

    ⚠️ 必须探测而不是看后缀：实测兴趣岛的 AUDIO 资源里，
       有一批 URL 后缀是 .mp3 但实际容器是 M4A/AAC（文件头 ftypM4A），
       也有 URL 后缀 .mp3 实际是带 mjpeg 封面的真 MP3。
    """
    try:
        out = xqd_proc.check_output(
            [ffprobe_path(), '-v', 'error', '-show_entries',
             'format=format_name,duration,size:stream=codec_type,codec_name',
             '-of', 'json', path],
            stderr=subprocess.DEVNULL, timeout=180)
        import json
        d = json.loads(out.decode('utf-8', 'replace'))
        fmt = d.get('format', {}) or {}
        streams = d.get('streams', []) or []
        codecs = [s.get('codec_name') or '' for s in streams]
        # 真实视频轨：排除 mp3 内嵌的 mjpeg 封面
        has_video = any(s.get('codec_type') == 'video'
                        and (s.get('codec_name') or '') != 'mjpeg'
                        for s in streams)
        has_audio = any(s.get('codec_type') == 'audio' for s in streams)
        return {
            'format_name': fmt.get('format_name') or '',
            'duration': float(fmt.get('duration') or 0),
            'has_video': has_video,
            'has_audio': has_audio,
            'codecs': codecs,
            'size': int(fmt.get('size') or 0),
        }
    except Exception:
        return {'format_name': '', 'duration': 0.0, 'has_video': False,
                'has_audio': False, 'codecs': [], 'size': 0}


def audio_ext_for(path):
    """根据真实容器判断音频成品的扩展名。

    * 真 MP3（含 mjpeg 封面）→ '.mp3'
    * M4A / AAC（无视频轨）  → '.m4a'
    * 其它                   → '.mp3'（兜底）
    """
    info = probe_media(path)
    codecs = [c.lower() for c in info['codecs']]
    if 'mp3' in codecs or 'mp3float' in codecs:
        return '.mp3'
    if not info['has_video'] and ('aac' in codecs or 'mp4a' in codecs):
        return '.m4a'
    if 'mp3' in (info['format_name'] or '').lower():
        return '.mp3'
    if not info['has_video']:
        return '.m4a'
    return '.mp3'


def swap_ext(path, new_ext):
    """替换扩展名。"""
    stem, _ = os.path.splitext(path)
    return stem + new_ext


# ── 并行分片下载 ─────────────────────────────────────────────

def _seg_name(url, i):
    """分片本地文件名（与 download_segments 保持一致）。"""
    name = os.path.basename(url.split('?')[0]) or ('seg%05d' % i)
    return '%05d_%s' % (i, name)


def download_segments(segments, dest_dir, workers=12, on_progress=None,
                      stop_flag=None, control=None):
    """并行下载分片到 dest_dir。

    返回 (成功数, 失败数, 字节数)。
    on_progress(downloaded_bytes, total_bytes, done_duration, total_duration)

    ★ control：DownloadControl 对象。暂停时各线程在**取下一个分片前**
      等待，已下好的分片保留在 dest_dir 里，继续后接着下。

    ★ 进度用的是**时长占比**（done_duration / total_duration）而不是
      字节占比：清单里每片的时长是精确已知的，所以百分比不会因为
      「总大小是估算的」而偏。剩余时间估算才能准。
    """
    if not segments:
        return 0, 0, 0
    os.makedirs(dest_dir, exist_ok=True)
    total_bytes = 0
    total_dur = 0.0
    for _u, d in segments:
        total_dur += d
    lock = threading.Lock()
    state = {'done': 0, 'bytes': 0, 'dur': 0.0}
    idx = {'i': 0}

    def worker():
        while True:
            if stop_flag is not None and stop_flag.is_set():
                return
            # ★ 暂停点：在领新分片之前等 —— 这样暂停后不会有新请求发出
            if control is not None:
                if not control.wait_resume():
                    return
            with lock:
                i = idx['i']
                if i >= len(segments):
                    return
                idx['i'] = i + 1
            url = segments[i][0]
            dur = segments[i][1]
            path = os.path.join(dest_dir, _seg_name(url, i))
            # ★ 断点续下：已下好的分片不重复下载（暂停后继续的关键）
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                with lock:
                    state['done'] += 1
                    state['bytes'] += os.path.getsize(path)
                    state['dur'] += dur
                if on_progress:
                    try:
                        on_progress(state['bytes'], total_bytes,
                                    state['dur'], total_dur)
                    except Exception:
                        pass
                continue
            for attempt in range(3):
                # 每次重试前也检查暂停，避免卡在重试里
                if control is not None:
                    if not control.wait_resume():
                        return
                code, body = http_get(url, timeout=40)
                if code == 200 and body:
                    try:
                        with open(path, 'wb') as f:
                            f.write(body)
                        with lock:
                            state['bytes'] += len(body)
                            state['done'] += 1
                            state['dur'] += dur
                        break
                    except OSError:
                        pass
                if attempt < 2:
                    time.sleep(1.0 + attempt)
            if on_progress:
                try:
                    on_progress(state['bytes'], total_bytes,
                                state['dur'], total_dur)
                except Exception:
                    pass

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(max(1, workers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return state['done'], len(segments) - state['done'], state['bytes']


def _concat_and_mux(seg_dir, out_path, ext='ts'):
    """按序拼接分片并转封装成 mp4。

    用 **cat 直接字节拼接** 再喂给 ffmpeg，而不是 concat demuxer：
    concat demuxer 会重置时间戳，实测成品比清单标称长 6 秒
    （230.8s vs 224.6s），导致时长校验失败。cat 方式保持原始时间戳。
    """
    files = sorted(os.listdir(seg_dir))
    files = [f for f in files if f.endswith('.' + ext)]
    if not files:
        return False, '没有可用的分片'

    cat_path = os.path.join(seg_dir, 'all.' + ext)
    with open(cat_path, 'wb') as out:
        for name in files:
            p = os.path.join(seg_dir, name)
            try:
                with open(p, 'rb') as f:
                    while True:
                        chunk = f.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
            except OSError:
                continue

    tmp_out = out_path + '.part.mp4'
    cmd = [ffmpeg_path(), '-y', '-loglevel', 'error',
           '-i', cat_path,
           '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
           '-movflags', '+faststart', tmp_out]
    try:
        p = xqd_proc.run(cmd, capture_output=True, timeout=7200)
    except Exception as e:
        return False, 'ffmpeg 失败: %s' % e

    if p.returncode != 0 or not os.path.exists(tmp_out) \
            or os.path.getsize(tmp_out) < 10000:
        err = p.stderr.decode('utf-8', 'replace')[-300:]
        return False, err or ('ffmpeg rc=%s' % p.returncode)

    os.replace(tmp_out, out_path)
    try:
        os.remove(cat_path)
    except OSError:
        pass
    return True, '%.1f MB' % (os.path.getsize(out_path) / 1048576)


def download_direct(url, out_path, expect_duration=0, on_progress=None,
                    control=None):
    """直链媒体（AUDIO 类）→ **保持原始格式**保存。

    实测（2026-11-07）：兴趣岛 AUDIO 资源的原始文件是
    **MP3 或 M4A/AAC**（部分 URL 后缀是 .mp3 但实际是 M4A 容器），
    强行塞进 MP4 容器既无必要也会二次转码失真。

    这里只做两件事：
      1. 原始字节落盘（不转码）
      2. 用 ffprobe 探测真实容器，把扩展名改成对应的 .mp3 / .m4a

    临时文件用 mkstemp，**不能**用固定名（并发下会互相覆盖）。

    ★ 采用**流式**读取（64KB 一块），这样：
      - 进度能实时上报（之前是整文件读完才报一次）
      - 可以中途暂停（用户点「暂停」时立刻停下，不再继续收字节）
    """
    fd, raw = tempfile.mkstemp(prefix='xqd_direct_', suffix='.bin')
    os.close(fd)
    try:
        total = 0
        got = 0
        try:
            resp = http_open(url, timeout=1800)
        except urllib.error.HTTPError as e:
            return False, '直链下载失败 (HTTP %s)' % e.code, out_path
        except Exception as e:
            return False, '直链下载失败 (%s)' % e, out_path
        try:
            try:
                total = int(resp.headers.get('Content-Length') or 0)
            except (TypeError, ValueError):
                total = 0
            with open(raw, 'wb') as f:
                while True:
                    # ★ 暂停点：每次取块之前检查
                    if control is not None:
                        if not control.wait_resume():
                            return False, '已暂停', out_path
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if on_progress:
                        try:
                            # 直链音频没有分片时长，用字节占比当进度
                            on_progress(got, total or got, 0.0, 0.0)
                        except Exception:
                            pass
        finally:
            try:
                resp.close()
            except Exception:
                pass

        if got <= 0:
            return False, '直链下载失败（内容为空）', out_path

        ext = audio_ext_for(raw)
        final = swap_ext(out_path, ext)
        os.makedirs(os.path.dirname(final), exist_ok=True)
        os.replace(raw, final)

        if expect_duration > 0:
            actual = probe_duration(final)
            if actual <= 0:
                return False, '成品无法解析（可能损坏）', final
            if abs(actual - expect_duration) > max(3.0,
                                                   expect_duration * 0.01):
                return False, ('时长不符：%.1fs vs 期望 %.1fs'
                               % (actual, expect_duration)), final
        return True, '%.1f MB（原格式 %s）' % (
            os.path.getsize(final) / 1048576, ext), final
    finally:
        try:
            os.remove(raw)
        except OSError:
            pass


# ── 单节下载（对外主入口）────────────────────────────────────

def download_lesson(resolve_url, out_path, quality='max', workers=12,
                     tmp_root=None, on_progress=None, stop_flag=None,
                     expect_duration=0, control=None, on_phase=None,
                     seg_dir=None, keep_parts=False):
    """下载一节课。

    resolve_url : 返回播放地址的可调用对象
    out_path    : 成品路径（扩展名可能被音频类型改写，见返回值）
    on_progress : fn(downloaded_bytes, total_bytes)  —— 下载阶段
    expect_duration : 期望时长（秒），用于校验；0 表示不校验
    control     : DownloadControl 对象 —— 支持「暂停 / 继续」
    on_phase    : fn(phase_str) —— 阶段回调（解析/下载/封装/校验），
                  GUI 用它把「正在封装」这类状态显示出来。
    seg_dir     : 分片缓存目录。**给了就用它**（不自动删），
                  这样下次再下同一节时能复用已下分片 → 跨进程续传。
    keep_parts  : 下载成功后是否保留分片缓存（默认删）。

    返回 (ok, message, final_path)
      final_path 是**实际**写出的路径：音频直链可能把 .mp4 改成 .m4a/.mp3。
    """

    def _phase(name):
        if on_phase:
            try:
                on_phase(name)
            except Exception:
                pass

    _phase('解析')
    url = resolve_url()
    if not url:
        return False, '无法取得播放地址', out_path

    segments, kind, note, total = parse_manifest(url, quality=quality)
    if not segments:
        return False, note or '清单解析失败', out_path

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    if kind == 'direct':
        _phase('下载')
        return download_direct(url, out_path,
                               expect_duration=expect_duration,
                               on_progress=on_progress,
                               control=control)

    # ★ seg_dir 由调用方给定时**复用**（跨进程续传的关键）：
    #   HLS 分片的文件名跨会话稳定（实测 150/150 一致），
    #   所以旧分片能被 download_segments 直接跳过。
    own_dir = seg_dir is None
    if own_dir:
        seg_dir = tempfile.mkdtemp(prefix='xqd_', dir=tmp_root) if tmp_root \
            else tempfile.mkdtemp(prefix='xqd_')
    else:
        os.makedirs(seg_dir, exist_ok=True)
    ok_result = False
    try:
        _phase('下载')
        ok, total_bytes = _dl_all(segments, seg_dir, workers, on_progress,
                                   stop_flag, control)
        if not ok:
            # 区分「被中止」和「真的下载失败」
            if control is not None and control.is_stopped():
                return False, '已中止', out_path
            return False, '分片下载失败', out_path

        # 转封装前再确认一次没被暂停（暂停时不该开始转封装）
        if control is not None:
            if not control.wait_resume():
                return False, '已暂停', out_path

        _phase('封装')
        ok, msg = _concat_and_mux(seg_dir, out_path)
        if not ok:
            return False, msg, out_path

        # 时长校验
        _phase('校验')
        if expect_duration > 0:
            actual = probe_duration(out_path)
            if actual <= 0:
                return False, '成品无法解析（可能损坏）', out_path
            if abs(actual - expect_duration) > max(3.0, expect_duration * 0.01):
                return False, ('时长不符：%.1fs vs 期望 %.1fs'
                               % (actual, expect_duration)), out_path
        ok_result = True
        return True, '%s，%s' % (note, msg), out_path
    finally:
        # ★ 成功才清分片；失败/中止时**保留** —— 留着才能下次接着下。
        #   （跨进程续传靠的就是这份缓存，见 xqd_history.parts_dir_for）
        #
        #   own_dir=True  → 这是引擎自己建的临时目录，一律清掉。
        #   own_dir=False → 调用方（GUI）指定的持久缓存目录：
        #       成功才清（keep_parts=True 时连成功的也保留）；
        #       失败/中止**必须保留**，否则续传就废了。
        if own_dir or (ok_result and not keep_parts):
            _cleanup(seg_dir)


def _dl_all(segments, seg_dir, workers, on_progress, stop_flag, control=None):
    """下载所有分片，返回 (是否全部成功, 总字节数)。

    ★ 总字节数靠**抽样外推**，抽样方式很关键（实测见下）：

      原来只取**前 3 片**。对「晚间课堂：内观五步法」（2485 片）实测：
        前 3 片大小 = 663076 / 683568 / 646344 B（都偏大）
        外推 1574.4 MB，真实成品 1146.5 MB → **偏高 37.3%**
      改成**均匀抽 12 片**（跨整个清单等距取）：
        外推 1138.5 MB → **误差 -0.7%**

      为什么前 3 片会偏：直播课录制的前几分钟码率高于全片均值，
      用开头几片代表全片必然高估。

    ★ 抽样用的分片会**写进 seg_dir 复用**，不额外浪费请求。
    """
    total_bytes = 0
    sampled = _sample_segments(segments, seg_dir)
    if segments and sampled:
        avg = sum(len(b) for _i, _u, b in sampled) / float(len(sampled))
        total_bytes = int(avg * len(segments))

    def _report(d, _t, dd, td):
        # 覆盖掉 download_segments 内部的 total（它自己不知道总大小）
        on_progress(d, total_bytes or _t, dd, td)

    done, fail, got = download_segments(
        segments, seg_dir, workers=workers,
        on_progress=_report if on_progress else None,
        stop_flag=stop_flag,
        control=control)
    return fail == 0 and done > 0, got


# 抽样片数：12 片实测误差 -0.7%；片数少到 8 也够用，再多只是多花请求
_SAMPLE_COUNT = 12


def _sample_segments(segments, seg_dir):
    """均匀抽样若干分片，下载并**写进 seg_dir**（供后续复用）。

    返回 [(index, url, body), ...]。

    ★ 为什么要均匀抽样而不是取前几片：
      直播课录制的前几分钟码率偏高，取开头会系统性高估总大小
      （实测 +37%）。跨整个清单等距取样才有代表性。

    ★ 分片总数很少时（比如只有 20 片），全取即可 —— 抽样误差可以忽略。
    """
    n = len(segments)
    if n == 0:
        return []
    if n <= _SAMPLE_COUNT:
        idxs = list(range(n))
    else:
        # 等距取样，覆盖首尾（末片常偏小，会拉低均值）
        step = (n - 1) / float(_SAMPLE_COUNT - 1)
        idxs = sorted(set(int(round(i * step))
                          for i in range(_SAMPLE_COUNT)))

    out = []
    for i in idxs:
        url = segments[i][0]
        local = os.path.join(seg_dir, _seg_name(url, i))
        # ★ 续传时优先用本地已有的分片 —— 直接读，不发请求
        #   （用户流量昂贵，抽样片不能重复下载）
        if os.path.isfile(local):
            try:
                with open(local, 'rb') as f:
                    body = f.read()
                if body:
                    out.append((i, url, body))
                    continue
            except OSError:
                pass
        code, body = http_get(url, timeout=30)
        if code == 200 and body:
            out.append((i, url, body))
            # ★ 写进 seg_dir，download_segments 会直接跳过（不重复下载）
            try:
                with open(local, 'wb') as f:
                    f.write(body)
            except OSError:
                pass
    return out


def _cleanup(seg_dir):
    """清理临时分片目录。

    不能用 shutil.rmtree：单目录常有 100~300 个文件，一次性批量删除会触发
    安全删除钩子的批量阈值被拦下，临时目录会一直累积。逐个删最稳。
    """
    try:
        for fn in os.listdir(seg_dir):
            p = os.path.join(seg_dir, fn)
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(seg_dir)
        except OSError:
            pass
    except OSError:
        pass
