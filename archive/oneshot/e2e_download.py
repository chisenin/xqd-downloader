# -*- coding: utf-8 -*-
"""端到端验证：API 拿清单 -> 判类型 -> 明文孪生 -> ffmpeg 下载 -> ffprobe 校验。

复用 docs/01-已验证事实.md 里已确认的规则，不再重新探测：
  - URL 三层：host / appId / <8hex><bizFileId> / <file>，rsplit('/', 2)
  - sign 只绑定目录和 t，不绑定文件名 -> 同目录其他文件可复用同一 sign
  - 请求明文孪生模板时必须去掉 encdomain=cmv1，否则 403
  - DRM 孪生名：voddrm.token.<JWT>.video_<num>_0.m3u8 -> 明文 v.f<num>.m3u8
  - 孪生必须做时长校验（容差 max(1.0, want*0.005)）
  - master 清单按短边 min(w,h) 选最清晰
  - ffmpeg 临时输出必须 .mp4 结尾
"""
import ssl
import urllib.request
import urllib.error
import json
import re
import os
import subprocess
import sys

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))

# ★ 凭据不在源码里 —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import xqd_creds            # noqa: E402

COOKIE = xqd_creds.load_cookie()

HOST = 'm.qianliao.net'
GATE = 'https://%s/financial/api/transfer' % HOST
UA = 'Mozilla/5.0 (Linux; Android 12; M2102K1C) okhttp/4.9.0'


def api(path, td, timeout=25):
    body = json.dumps({'transferData': td}).encode()
    h = {'User-Agent': UA, 'Cookie': COOKIE, 'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://%s' % HOST, 'Referer': 'https://%s/' % HOST,
         'Content-Type': 'application/json;charset=UTF-8'}
    req = urllib.request.Request(GATE + path, data=body, headers=h, method='POST')
    r = OP.open(req, timeout=timeout)
    return json.loads(r.read().decode('utf-8', 'replace'))


def fetch(url, referer=None, timeout=25):
    h = {'User-Agent': UA, 'Cookie': COOKIE, 'Accept': '*/*'}
    if referer:
        h['Referer'] = referer
    req = urllib.request.Request(url, headers=h)
    try:
        r = OP.open(req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300]


def parse_master(text):
    """返回 [(url, short_edge, w, h)]"""
    out = []
    lines = [l.strip() for l in text.splitlines()]
    for i, l in enumerate(lines):
        if l.startswith('#EXT-X-STREAM-INF'):
            m = re.search(r'RESOLUTION=(\d+)x(\d+)', l)
            if not m:
                continue
            w, h = int(m.group(1)), int(m.group(2))
            url = None
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j] and not lines[j].startswith('#'):
                    url = lines[j]
                    break
            if url:
                out.append((url, min(w, h), w, h))
    return out


def total_seconds(text):
    return sum(float(x) for x in re.findall(r'#EXTINF:\s*([\d.]+)', text))


def dir_of(url):
    """host/appId/<8hex><bizFileId>/<file> -> 目录部分与文件名"""
    p = url.split('://', 1)[1]
    parts = p.split('/')
    return '/'.join(parts[:-1]), parts[-1]


def sibling(url, newname):
    """同目录换文件名，保留 query"""
    d, _ = dir_of(url)
    q = url.split('?', 1)[1] if '?' in url else ''
    return 'https://%s/%s%s' % (d, newname, ('?' + q) if q else '')


def strip_encdomain(url):
    return re.sub(r'[?&]encdomain=cmv1', '', url)


def main():
    camp = sys.argv[1] if len(sys.argv) > 1 else '5721891467'
    work = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dl_test')
    os.makedirs(work, exist_ok=True)

    js = api('/gate/course/playListOfCourse', {'campId': camp, 'onlyCourseCatalogue': True})
    courses = js['data']['courses']
    print('课程数: %d' % len(courses))

    targets = [c for c in courses if c.get('type') in ('VIDEO', 'INTELLIGENT_LIVE')][:6]
    for c in targets:
        name = c.get('name')
        td = {'videoHost': None, 'roomId': c.get('roomId'),
              'topicId': c.get('topicId'), 'businessId': camp, 'businessType': 'camp'}
        try:
            js2 = api('/gate/course/getCoursePlayUrl', td)
            cpu = js2['data']['coursePlayUrl']
        except Exception as e:
            print('\n[%s] getCoursePlayUrl 失败: %s' % (name, e))
            continue
        url = cpu.get('playUrl')
        want = float(cpu.get('totalSeconds') or c.get('duration') or 0)
        print('\n=== %s' % name)
        print('  URL   : %s' % url)
        print('  时长  : API=%s' % want)

        st, body = fetch(url)
        print('  清单  : HTTP %s  %d bytes' % (st, len(body)))
        if st != 200:
            print('  !! 清单拉取失败')
            continue
        text = body.decode('utf-8', 'replace')
        kind = ('drm' if 'EXT-X-KEY' in text else
                'master' if 'EXT-X-STREAM-INF' in text else 'media')
        print('  类型  : %s' % kind)

        src = url
        if kind == 'master':
            variants = parse_master(text)
            print('  码率  : %s' % [(v[1], '%dx%d' % (v[2], v[3])) for v in variants])
            if variants:
                best = max(variants, key=lambda v: v[1])
                src = best[0]
                if not src.startswith('http'):
                    src = 'https://' + dir_of(url)[0] + '/' + src
                print('  选流  : 短边 %d -> %s' % (best[1], src))
                st2, b2 = fetch(src)
                text2 = b2.decode('utf-8', 'replace')
                print('  子清单: HTTP %s %d bytes  时长=%s' % (st2, len(b2), total_seconds(text2)))
        elif kind == 'drm':
            # DRM -> 找明文孪生
            m = re.search(r'video_(\d+)_', text) or re.search(r'v\.f(\d+)\.m3u8', text)
            num = m.group(1) if m else None
            print('  孪生号: %s' % num)
            if num:
                twin = sibling(url, 'v.f%s.m3u8' % num)
                twin = strip_encdomain(twin)
                st2, b2 = fetch(twin)
                t2 = b2.decode('utf-8', 'replace')
                got = total_seconds(t2)
                print('  孪生  : HTTP %s %d bytes  时长=%s (want %s)'
                      % (st2, len(b2), got, want))
                tol = max(1.0, want * 0.005)
                if st2 == 200 and abs(got - want) <= tol:
                    print('  ✓ 时长校验通过，用孪生')
                    src = twin
                else:
                    print('  ✗ 孪生不可用（时长不符或拉取失败）')
        else:
            got = total_seconds(text)
            print('  清单时长: %s' % got)

        # 下载
        safe = re.sub(r'[\\/:*?"<>|\r\n\t]', '_', name)
        out = os.path.join(work, safe + '.mp4')
        cmd = ['ffmpeg', '-y', '-loglevel', 'error',
               '-protocol_whitelist', 'file,http,https,tcp,tls,crypto,httpproxy',
               '-progress', 'pipe:1', '-nostats',
               '-i', src, '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
               '-movflags', '+faststart', out + '.part.mp4']
        print('  下载中: %s' % os.path.basename(out))
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=600)
            part = out + '.part.mp4'
            if os.path.exists(part) and os.path.getsize(part) > 0:
                os.replace(part, out)
                print('  ✓ 下载完成 %.1f MB' % (os.path.getsize(out) / 1048576.0))
            else:
                print('  ✗ 下载失败: %s' % p.stderr.decode('utf-8', 'replace')[:300])
        except Exception as e:
            print('  ✗ 下载异常: %s' % e)
            continue

        try:
            pr = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                 'format=duration,size:stream=codec_name,width,height',
                                 '-of', 'json', out], capture_output=True, timeout=60)
            info = json.loads(pr.stdout.decode('utf-8', 'replace'))
            dur = float(info['format']['duration'])
            v = next((s for s in info.get('streams', []) if s.get('width')), {})
            a = next((s for s in info.get('streams', []) if s.get('codec_name') == 'aac'), {})
            print('  ✓ ffprobe: %.1fs  %s %sx%s  aac=%s  (清单 %s, 差 %.2fs)'
                  % (dur, v.get('codec_name'), v.get('width'), v.get('height'),
                     bool(a), want, abs(dur - want)))
        except Exception as e:
            print('  ffprobe 失败: %s' % e)


if __name__ == '__main__':
    main()
