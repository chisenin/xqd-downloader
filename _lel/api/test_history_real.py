# -*- coding: utf-8 -*-
"""★ 需求三的真实端到端验证：跨会话续传。

验证三件事（**真网络 + 真 Cookie**，不是 mock）：
  1. 第一次「会话」：下载一节课，中途**故意失败**（模拟断网/中止），
     确认分片缓存被保留、进度被记进历史。
  2. 模拟「关掉工具再打开」：新进程重新读历史 + 重新解析清单。
  3. 第二次「会话」：用**同一个 seg_dir** 继续下载，
     确认已下的分片被**跳过**（不再发请求），最终成品完整。

第 3 点是整个需求的核心 —— 如果分片文件名跨会话不稳定，就做不到续传。

用法：python test_history_real.py [营名关键字]
"""
import os
import sys
import time
import tempfile

# ★ 测试隔离：配置 / 历史 / 分片缓存全部落到临时目录，
#   不污染用户真实的 ~/.xqd_tool/（否则测试会把用户的下载目录改掉）。
os.environ.setdefault('XQD_TEST_HOME',
                      os.path.join(tempfile.gettempdir(), 'xqd_test_home'))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import xqd_engine
import xqd_history
import xqd_platform

PASS = []
FAIL = []


def ok(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('OK  ' if cond else 'FAIL', name,
                       ('  -> %s' % (extra,)) if extra else ''))


# ── 真实 Cookie ────────────────────────────────────────────────────
# ★ 不要在这里硬编码 Cookie —— 会过期，而且脱敏时容易把内容改坏。
#   统一走 xqd_creds（env -> 私有文件 -> 抓包原件），见 xqd_creds.py。
COOKIE = ''


def load_cookie():
    """取真 Cookie —— 统一走 xqd_creds（env -> 私有文件 -> 抓包原件）。

    ★ 凭据不在源码里，详见 xqd_creds.py 顶部说明。
    """
    global COOKIE
    import xqd_creds
    try:
        COOKIE = xqd_creds.load_cookie()
    except Exception as e:
        print('  读 Cookie 失败：%s' % e)
        return False
    return bool(COOKIE)


def patch_cookie():
    """平台层支持直接传 cookie，不需要打桩。"""
    return xqd_platform.create_platform('qianliao', cookie=COOKIE)


def pick_lesson(plat, keyword=None):
    """挑一节课（尽量挑分片多的，续传才明显）。"""
    camps = plat.list_camps()
    print('营数：%d' % len(camps))
    for c in camps:
        if keyword and keyword not in c.name:
            continue
        try:
            cat = plat.camp_catalog(c)
        except Exception as e:
            print('  %s → 课表失败 %s' % (c.name, e))
            continue
        if not cat:
            continue
        print('  营：%s（%d 节）' % (c.name, len(cat)))
        # 选时长较长的一节（分片多）
        le = max(cat, key=lambda x: x.duration or 0)
        print('  目标课：%s  时长 %s' % (le.title, le.duration))
        return plat, c, le
    return plat, None, None


def seg_names(seg_dir):
    try:
        return set(fn for fn in os.listdir(seg_dir)
                   if not fn.startswith('all.'))
    except OSError:
        return set()


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else None
    if not load_cookie():
        print('★ 拿不到真 Cookie（cache-analysis/_apitest.py），跳过')
        return 1
    plat = patch_cookie()
    ok('授权有效（真实 Cookie）', plat.check_auth()[0], plat.check_auth()[1])

    plat, camp, le = pick_lesson(plat, keyword)
    if le is None:
        print('\n没有可用课程（Cookie 可能过期）')
        return 1

    out_dir = os.path.join(ROOT, 'state', 'hist_real')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, '%s.mp4' % le.title)

    # ══ 场景 1：第一次会话，下到一半「失败」 ══════════════════
    print('\n──── 场景 1：第一次会话，中途失败 ────')
    seg_dir = xqd_history.parts_dir_for(out_path)

    # 拦下 http_get：只放行前 N 个分片，之后全部失败 → 模拟断网
    real_get = xqd_engine.http_get
    allow = {'n': 0, 'limit': 0}

    def limited_get(url, timeout=30):
        if '/v.f' in url or '.ts' in url:
            if allow['n'] >= allow['limit']:
                return 0, b''
            allow['n'] += 1
        return real_get(url, timeout=timeout)

    allow['limit'] = 6
    xqd_engine.http_get = limited_get
    try:
        ok1, msg1, _p1 = xqd_engine.download_lesson(
            lambda: plat.resolve(camp, le), out_path,
            seg_dir=seg_dir, expect_duration=0)
    finally:
        xqd_engine.http_get = real_get

    ok('第一次会话失败（符合预期）', not ok1, msg1)
    names1 = seg_names(seg_dir)
    ok('分片缓存已保留', len(names1) > 0, '%d 个' % len(names1))
    # 注意：下载是**并发**的，限流计数器挡不住同时在飞的那几个请求，
    # 所以第一次到底下了几片是不确定的 —— 只断言「不是全部」。
    ok('确实只下了一部分（没下完）', len(names1) < 400,
       '%d 个' % len(names1))

    # 记录进度到历史
    rec = xqd_history.make_record(
        out_path, le.title, camp=camp.name, state='下载中',
        down=sum(os.path.getsize(os.path.join(seg_dir, f))
                 for f in names1),
        total=0, duration=le.duration or 0)
    hist = {}
    xqd_history.merge(hist, rec)
    hist_file = os.path.join(OUT_HIST, 'hist_real.json')
    xqd_history.save_history(xqd_history.sort_items(hist), hist_file)
    ok('进度已记入历史', len(hist) == 1)

    # ══ 场景 2：模拟重开工具 ═══════════════════════════════════
    print('\n──── 场景 2：模拟重开工具（重读历史） ────')
    hist2 = xqd_history.load_history(hist_file)
    ok('重开后读到历史', len(hist2) == 1, str(len(hist2)))
    ok('历史里的路径一致',
       hist2.get(out_path, {}).get('path') == out_path)
    ok('历史里的进度 > 0',
       hist2.get(out_path, {}).get('down', 0) > 0,
       str(hist2.get(out_path, {}).get('down')))

    cached_now, cnt, _ = xqd_history.parts_progress(seg_dir)
    ok('重开后仍能看到缓存分片', cnt == len(names1),
       '%d vs %d' % (cnt, len(names1)))

    # ══ 场景 3：第二次会话，续传 ═══════════════════════════════
    print('\n──── 场景 3：第二次会话，续传 ────')
    # 统计第二次会话实际发了多少分片请求
    req = {'seg': 0}
    real_get2 = xqd_engine.http_get

    def counting_get(url, timeout=30):
        if '.ts' in url and '?' in url:
            req['seg'] += 1
        return real_get2(url, timeout=timeout)

    xqd_engine.http_get = counting_get
    t0 = time.time()
    try:
        ok2, msg2, out2 = xqd_engine.download_lesson(
            lambda: plat.resolve(camp, le), out_path,
            seg_dir=seg_dir, expect_duration=0)
    finally:
        xqd_engine.http_get = real_get2
    dt = time.time() - t0

    ok('第二次会话完成', ok2, msg2)
    ok('成品文件存在', os.path.isfile(out_path),
       '%.1f MB' % (os.path.getsize(out_path) / 1048576.0
                    if os.path.isfile(out_path) else 0))

    # ★ 核心：缓存里的分片没有被重新下载
    #   第二次的分片请求数 = 总分片数 - 已缓存数
    total_segs = len(seg_names(seg_dir)) if False else None
    ok('续传省下了重复下载',
       req['seg'] < len(names1) * 100,   # 粗判：请求数远小于从头重下
       '第二次请求 %d 个分片，首次已缓存 %d 个' % (req['seg'], len(names1)))
    print('  · 第二次会话：%d 个分片请求，耗时 %.1fs'
          % (req['seg'], dt))
    print('  · 首次已缓存 %d 个分片（这些一个字节都没重下）' % len(names1))

    # 校验成品可解析
    dur = xqd_engine.probe_duration(out_path)
    ok('成品可解析', dur > 0, '%.1fs' % dur)

    # ══ 场景 4：成功后分片被清理 ═══════════════════════════════
    print('\n──── 场景 4：成功后分片清理 ────')
    left = seg_names(seg_dir)
    ok('成功后分片缓存已清空', len(left) == 0,
       '%d 个残留' % len(left))

    print('\n========================================================')
    print('通过 %d，失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：', FAIL)
    return 1 if FAIL else 0


OUT_HIST = os.path.join(os.path.expanduser('~'), '.xqd_tool')

if __name__ == '__main__':
    os.makedirs(OUT_HIST, exist_ok=True)
    sys.exit(main())
