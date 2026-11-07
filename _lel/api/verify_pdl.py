# -*- coding: utf-8 -*-
"""单节并行下载验证：测速度 + 校验时长。

用法: python _lel/api/verify_pdl.py <营名> [第几节(0-based)] [输出目录]
"""
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import xqd_api as API   # noqa: E402
import xqd_pdl as P     # noqa: E402
import xqd_app as A     # noqa: E402

TMP = os.path.join(ROOT, 'state', 'pdl_tmp')


def main():
    camp = sys.argv[1] if len(sys.argv) > 1 else '引气归源太极营'
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    out_root = sys.argv[3] if len(sys.argv) > 3 else 'Z:/太极营'

    items = API.camp_catalog(camp)
    it = items[idx]
    print('营=%s  第%d节=%s  时长=%ss' % (camp, idx, it['title'], it.get('duration')))

    url = API.resolve(camp, it)
    print('URL: %s' % url)

    t0 = time.time()
    segs, kind, note, dur = P.manifest_segments(url)
    if not segs:
        print('清单解析失败: %s' % note)
        return 1
    print('类型=%s %s  分片=%d  清单时长=%.1fs  (解析 %.1fs)'
          % (kind, note, len(segs), dur, time.time() - t0))

    folder = os.path.join(out_root, A.safe_name(camp))
    os.makedirs(folder, exist_ok=True)
    out_path = os.path.join(folder, A.safe_name(it['title']) + '.mp4')

    seg_dir = os.path.join(TMP, '%s_%d' % (camp, idx))
    if os.path.isdir(seg_dir):
        shutil.rmtree(seg_dir)

    f = P.SegFetcher(workers=12)
    t1 = time.time()
    ok, n = f.fetch_all(segs, seg_dir,
                        progress=lambda i, t: print('  分片 %d/%d  %.1f MB  %.2f MB/s'
                                                    % (i, t, f.done_bytes / 1048576,
                                                       f.done_bytes / 1048576 /
                                                       max(0.01, time.time() - t1)),
                                                flush=True))
    dt = time.time() - t1
    print('分片下载: %d 个, %.1f MB / %.1fs = %.2f MB/s  失败=%d'
          % (n, f.done_bytes / 1048576, dt, f.done_bytes / 1048576 / max(dt, 0.01),
             len(f.failed)))
    if not ok:
        print('有分片失败，样本:', f.failed[:3])
        return 1

    t2 = time.time()
    mok, mnote = P.mux(seg_dir, out_path, n)
    print('转封装: %s  %s  (%.1fs)' % (mok, mnote, time.time() - t2))
    if not mok:
        return 1

    pd = P.probe_duration(out_path)
    exp = it.get('duration') or 0
    print('时长校验: 实际=%.1fs  期望=%.1fs  误差=%.2fs'
          % (pd, exp, abs(pd - exp) if pd and exp else -1))
    print('输出: %s  (%.1f MB)' % (out_path, os.path.getsize(out_path) / 1048576))
    shutil.rmtree(seg_dir, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
