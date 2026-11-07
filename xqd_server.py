# -*- coding: utf-8 -*-
"""兴趣岛课程导出 —— 本地服务。

    python xqd_server.py [--port 8765] [--out "D:/user/chisenin/Videos"]

提供 JSON API：
    GET  /api/state              当前状态（连接、缓存、正在进行的任务）
    GET  /api/camps?tab=正式营    列出该标签下的营
    GET  /api/courses?camp=xxx    某营的课表
    POST /api/sweep   {camp}      逐节绑定 fileId（后台任务，仅 ADB 模式需要）
    POST /api/download {camp, items:[{title,when}]}  下载选中课程
    GET  /api/files?camp=xxx      已下载文件清单
    POST /api/settings {out}      修改输出目录

两种数据源（--mode）：
    api  默认。用 Cookie 直连业务网关，**不需要模拟器**。
         整个营的课表一次拿全，播放地址现场解析（签名天然新鲜），
         因此不需要「sweep」这一步。
    adb  旧路径。用模拟器逐节播放绑定 fileId。

ADB 操作是**串行**的（同一台模拟器不能并发操作），所有涉及 UI 的动作
统一放进 adb_lock 保护的队列里；下载是纯网络/文件操作，可并发。
"""
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import xqd                                                    # noqa: E402
import xqd_app as A                                           # noqa: E402
import xqd_api as API                                         # noqa: E402

OUT_ROOT = 'D:/user/chisenin/Videos'
PORT = 8765
MODE = 'api'              # 'api' | 'adb'

# ── 全局状态 ──────────────────────────────────────────────────────
LOCK = threading.RLock()
STATE = {
    'adb_connected': False,
    'adb_locked': False,     # 是否正有任务占用模拟器
    'tasks': [],             # 任务列表
    'out_root': OUT_ROOT,
    'last_error': '',
    'mode': MODE,
}

TASK_SEQ = [0]


def new_task(kind, title, detail=''):
    with LOCK:
        TASK_SEQ[0] += 1
        t = {'id': TASK_SEQ[0], 'kind': kind, 'title': title,
             'detail': detail, 'state': 'running', 'progress': 0.0,
             'current': '', 'ok': 0, 'fail': 0, 'log': [],
             'started': time.time()}
        STATE['tasks'].insert(0, t)
        del STATE['tasks'][40:]
        return t


def task_log(t, msg):
    with LOCK:
        t['log'].append('%s %s' % (time.strftime('%H:%M:%S'), msg))
        del t['log'][-200:]
    A.log(msg)


def finish_task(t, state='done'):
    with LOCK:
        t['state'] = state
        t['finished'] = time.time()
        t['progress'] = 100.0 if state == 'done' else t['progress']


# ── ADB 串行锁 ────────────────────────────────────────────────────
ADB_LOCK = threading.Lock()


def adb_guard():
    return ADB_LOCK


def ensure_connected():
    with LOCK:
        STATE['adb_connected'] = True
    xqd.connect()


# ══════════════════════════ 业务动作 ══════════════════════════

def do_list_camps(tab):
    if MODE == 'api':
        camps = API.list_camps(tab)
        return {'camps': camps, 'mode': 'api'}
    ensure_connected()
    with adb_guard():
        camps = A.list_camps(tab)
    out = []
    for c in camps:
        out.append({'name': c['name'],
                    'badge': c['badge'],
                    'type': A._badge_type(c['badge']),
                    'count': A._badge_count(c['badge'])})
    return {'camps': out, 'mode': 'adb'}


def do_catalog(camp):
    if MODE == 'api':
        cat = API.camp_catalog(camp)
        # API 模式下所有课都能现场解析出播放地址 -> resolved 恒为 True
        items = [{'title': c['title'], 'when': c['when'],
                  'index': c['index'], 'resolved': True,
                  'duration': c.get('duration'), 'type': c.get('type')}
                 for c in cat]
        return {'camp': camp, 'items': items, 'mode': 'api'}

    ensure_connected()
    with adb_guard():
        cat = A.camp_catalog(camp)
    A._save(A.CATALOG_FILE, dict(A._load(A.CATALOG_FILE, {}), **{camp: cat}))
    # 补上 fileId 映射情况
    names = A._load(A.NAMES_FILE, {})
    by_title = {}
    for bid, info in names.items():
        if info.get('camp') == camp:
            by_title.setdefault(info.get('name'), bid)
    items = []
    for c in cat:
        items.append({'title': c['title'], 'when': c['when'],
                      'index': c['index'],
                      'resolved': c['title'] in by_title})
    return {'camp': camp, 'items': items, 'mode': 'adb'}


def _run_sweep_guarded(camp, task):
    try:
        run_sweep(camp, task)
    except Exception as e:
        task_log(task, '异常终止：%s' % e)
        task['state'] = 'error'
        STATE['last_error'] = traceback.format_exc()[-600:]
        task['finished'] = time.time()


def run_sweep(camp, task):
    if MODE == 'api':
        # API 模式不需要 sweep：课表一次拿全，播放地址现场解析
        task_log(task, 'API 模式无需绑定 fileId（课表已一次性取全）')
        task['ok'] = 0
        finish_task(task, 'done')
        return
    ensure_connected()

    def prog(done, total, title):
        with LOCK:
            task['current'] = title
            if total:
                task['progress'] = min(99.0, done * 100.0 / total)

    try:
        with adb_guard():
            played, newmap = A.sweep_camp(camp, progress=prog)
        task['ok'] = played
        finish_task(task, 'done')
    except Exception as e:
        task_log(task, '异常：%s' % e)
        task['state'] = 'error'
        STATE['last_error'] = traceback.format_exc()[-600:]


def run_download(camp, items, task):
    if MODE == 'api':
        run_download_api(camp, items, task)
        return
    ensure_connected()
    names = A._load(A.NAMES_FILE, {})
    links = A._load(A.LINKS_FILE, {})
    by_title = {}
    for bid, info in names.items():
        if info.get('camp') == camp:
            by_title.setdefault(info.get('name'), bid)

    out_root = STATE['out_root']
    folder = os.path.join(out_root, A.safe_name(camp))
    os.makedirs(folder, exist_ok=True)

    ok = fail = skip = 0
    total = len(items)
    for i, it in enumerate(items):
        title = it.get('title')
        out_path = os.path.join(folder, A.safe_name(title) + '.mp4')
        with LOCK:
            task['current'] = '准备：%s' % title
            task['progress'] = i * 100.0 / total
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
            task_log(task, '已存在，跳过：%s' % title)
            skip += 1
            with LOCK:
                task['progress'] = (i + 1) * 100.0 / total
            continue

        bid = by_title.get(title)
        url = (links.get(bid) or {}).get('url')
        if not url:
            task_log(task, '没有链接（未绑定 fileId）：%s' % title)
            fail += 1
            with LOCK:
                task['progress'] = (i + 1) * 100.0 / total
            continue

        # 签名可能过期 → 失效则回模拟器重新绑定
        if not A.probe_alive(url):
            task_log(task, '链接已过期，重新绑定：%s' % title)
            with adb_guard():
                A.sweep_camp(camp)
            names = A._load(A.NAMES_FILE, {})
            links = A._load(A.LINKS_FILE, {})
            bid = by_title.get(title)
            url = (links.get(bid) or {}).get('url')
            if not url:
                fail += 1
                continue

        with LOCK:
            task['current'] = title
            task['progress'] = i * 100.0 / total

        def dg(pct, _t=title):
            with LOCK:
                task['progress'] = (i + pct / 100.0) * 100.0 / total
                task['current'] = '%s（%.0f%%）' % (_t, pct)
        good, note, _ = A.download(url, out_path, progress=dg)
        if good:
            ok += 1
            size = os.path.getsize(out_path) / 1048576.0
            task_log(task, '✓ %s  [%.1fMB] %s' % (title, size, note))
        else:
            fail += 1
            task_log(task, '✗ %s  %s' % (title, note[:160]))
        with LOCK:
            task['progress'] = (i + 1) * 100.0 / total
    task['ok'] = ok
    task['fail'] = fail
    task['skip'] = skip
    finish_task(task, 'done')


def run_download_api(camp, items, task):
    """API 模式下载：现场解析播放地址，不需要预先绑定 fileId。"""
    out_root = STATE['out_root']

    def lg(msg):
        task_log(task, msg)

    def pg(done, total, title):
        with LOCK:
            task['current'] = title
            if total:
                task['progress'] = min(99.0, done * 100.0 / total)

    try:
        ok, fail, skip = API.download_items(
            camp, items, task_log=lg,
            progress=lambda frac, total, title: pg(frac, total, title),
            out_root=out_root)
    except Exception as e:
        task_log(task, '异常终止：%s' % e)
        task['state'] = 'error'
        STATE['last_error'] = traceback.format_exc()[-600:]
        task['finished'] = time.time()
        return
    task['ok'] = ok
    task['fail'] = fail
    task['skip'] = skip
    finish_task(task, 'done')


def _run_download_guarded(camp, items, task):
    """包一层异常保护 —— 任何异常都要把任务标记为 error，不能静默挂起。"""
    try:
        run_download(camp, items, task)
    except Exception as e:
        task_log(task, '异常终止：%s' % e)
        task['state'] = 'error'
        STATE['last_error'] = traceback.format_exc()[-600:]
        task['finished'] = time.time()


def do_files(camp=None):
    root = STATE['out_root']
    out = []
    if camp:
        folder = os.path.join(root, A.safe_name(camp))
        if os.path.isdir(folder):
            for fn in os.listdir(folder):
                p = os.path.join(folder, fn)
                if fn.lower().endswith('.mp4'):
                    out.append({'camp': camp, 'name': fn,
                                'size': os.path.getsize(p),
                                'path': p})
    else:
        for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            folder = os.path.join(root, d)
            if not os.path.isdir(folder):
                continue
            for fn in os.listdir(folder):
                if fn.lower().endswith('.mp4'):
                    p = os.path.join(folder, fn)
                    out.append({'camp': d, 'name': fn,
                                'size': os.path.getsize(p), 'path': p})
    return {'files': out, 'out_root': root}


# ══════════════════════════ HTTP ══════════════════════════

UI_PATH = os.path.join(HERE, 'ui.html')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path in ('/', '/index.html'):
                with io.open(UI_PATH, encoding='utf-8') as f:
                    self._send(200, f.read(), 'text/html; charset=utf-8')
                return
            if u.path == '/api/state':
                with LOCK:
                    self._json({
                        'adb_connected': STATE['adb_connected'],
                        'adb_busy': STATE['adb_locked'],
                        'out_root': STATE['out_root'],
                        'tasks': STATE['tasks'][:12],
                        'last_error': STATE['last_error'],
                        'mode': STATE.get('mode', MODE),
                    })
                return
            if u.path == '/api/camps':
                tab = (q.get('tab') or ['全部'])[0]
                self._json(do_list_camps(tab))
                return
            if u.path == '/api/courses':
                camp = (q.get('camp') or [''])[0]
                if not camp:
                    self._json({'error': '缺少 camp'}, 400)
                    return
                self._json(do_catalog(camp))
                return
            if u.path == '/api/files':
                camp = (q.get('camp') or [''])[0] or None
                self._json(do_files(camp))
                return
            self._json({'error': 'not found'}, 404)
        except Exception as e:
            self._json({'error': str(e),
                        'trace': traceback.format_exc()[-800:]}, 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else b'{}'
        try:
            body = json.loads(raw.decode('utf-8'))
        except ValueError:
            body = {}
        try:
            if u.path == '/api/sweep':
                camp = body.get('camp') or ''
                if not camp:
                    self._json({'error': '缺少 camp'}, 400)
                    return
                t = new_task('sweep', '绑定 %s' % camp)
                threading.Thread(target=_run_sweep_guarded,
                                 args=(camp, t), daemon=True).start()
                self._json({'task': t['id']})
                return
            if u.path == '/api/download':
                camp = body.get('camp') or ''
                items = body.get('items') or []
                if not camp or not items:
                    self._json({'error': '缺少 camp 或 items'}, 400)
                    return
                t = new_task('download', '下载 %s（%d 节）'
                             % (camp, len(items)))
                threading.Thread(target=_run_download_guarded,
                                 args=(camp, items, t), daemon=True).start()
                self._json({'task': t['id']})
                return
            if u.path == '/api/settings':
                out = body.get('out')
                if out:
                    STATE['out_root'] = out
                    os.makedirs(out, exist_ok=True)
                self._json({'out_root': STATE['out_root']})
                return
            if u.path == '/api/open_folder':
                p = body.get('path') or STATE['out_root']
                if os.path.isdir(p):
                    os.startfile(p)          # noqa: S606
                self._json({'ok': True})
                return
            self._json({'error': 'not found'}, 404)
        except Exception as e:
            self._json({'error': str(e),
                        'trace': traceback.format_exc()[-800:]}, 500)


def main():
    global OUT_ROOT, PORT, MODE
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == '--port' and i + 1 < len(args):
            PORT = int(args[i + 1])
        if a == '--out' and i + 1 < len(args):
            OUT_ROOT = args[i + 1]
        if a == '--mode' and i + 1 < len(args):
            MODE = args[i + 1]
    STATE['out_root'] = OUT_ROOT
    STATE['mode'] = MODE
    os.makedirs(OUT_ROOT, exist_ok=True)

    if MODE == 'api':
        A.log('数据源：API 直连（不需要模拟器）')
        try:
            camps = API.list_camps('正式营')
            A.log('已连通兴趣岛网关，正式营 %d 个' % len(camps))
        except Exception as e:
            A.log('网关连接失败：%s' % e)
    else:
        A.log('数据源：模拟器（ADB）')
        A.log('正在连接 MuMu 模拟器…')
        try:
            ensure_connected()
            A.log('模拟器已连接')
        except Exception as e:
            A.log('模拟器连接失败：%s' % e)

    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    A.log('')
    A.log('  兴趣岛课程导出工具已启动')
    A.log('  http://127.0.0.1:%d' % PORT)
    A.log('  输出目录：%s' % OUT_ROOT)
    A.log('')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
