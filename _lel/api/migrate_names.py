# -*- coding: utf-8 -*-
"""把已下载的旧命名成品迁移到新命名规则。

背景
----
命名规则从「<课名>.mp4」改成「<序号>.<课名>.<YYYY.MM.DD>.mp4」后，
磁盘上已有的旧文件不会被 batch 的"已存在"判定认领（文件名对不上），
会被重复下载一遍 —— 流量昂贵，必须避免。

做法
----
1. **一次 listdir** 拿到营目录下的全部旧文件（Z 盘是 SMB 网络盘，
   逐个 os.path.exists 探测几百个候选名会慢到不可用 —— 实测 8 分钟没跑完）。
2. 按课名把旧文件归类（`<课名>.mp4`、`<课名> (2).mp4`、`<课名>.part.mp4` …）。
3. 同一课名可能有多个旧文件（上次并发 bug 产出过一个正常一个截断的），
   用**时长校验**挑出正确的那个改名成新名字，其余移入 `_trash_旧命名/`。
4. 找不到旧文件的课 = 还没下过，交给 batch 正常下载。

用法:
  python -u _lel/api/migrate_names.py --out "Z:/太极营"
  python -u _lel/api/migrate_names.py --out "Z:/太极营" --dry
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '_lel', 'api'))

import xqd_api as API      # noqa: E402
import xqd_app as A        # noqa: E402
import xqd_pdl as P        # noqa: E402


def log(msg):
    print(msg, flush=True)


def scan_old(folder):
    """一次 listdir，返回 {课名: [(路径, 大小)]}。

    只认 .mp4（含 .part.mp4 残留）；命名形如
      <课名>.mp4 / <课名> (2).mp4 / <课名> (3).mp4 / <课名>.part.mp4
    """
    out = {}
    if not os.path.isdir(folder):
        return out
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for fn in names:
        if not fn.lower().endswith('.mp4'):
            continue
        p = os.path.join(folder, fn)
        try:
            size = os.path.getsize(p)
        except OSError:
            continue
        if size < 100000:          # 太小的肯定不是成品
            continue
        stem = fn[:-4]
        stem = re.sub(r'\.part$', '', stem)
        m = re.match(r'^(.*) \(\d+\)$', stem)
        if m:
            stem = m.group(1)
        out.setdefault(stem, []).append((p, size))
    return out


def pick_by_duration(cands, expect):
    """在多个旧文件里挑时长与期望一致的。

    expect<=0（课表没给 duration）时挑最大的那个。
    返回 (good_path, [其余的])
    """
    if expect <= 0:
        best = max(cands, key=lambda x: x[1])
        return best[0], [c[0] for c in cands if c[0] != best[0]]
    good = None
    for p, _sz in cands:
        pd = P.probe_duration(p)
        if pd > 0 and abs(pd - expect) <= max(3.0, expect * 0.01):
            good = p
            break
    if good:
        return good, [c[0] for c in cands if c[0] != good]
    # 没有合格的 → 最大的当坏文件处理
    best = max(cands, key=lambda x: x[1])
    return None, [c[0] for c in cands]


def migrate_camp(camp, out_root, trash_dir, dry=False):
    """迁移一个营。返回 (renamed, trashed, missing)。"""
    cat = API.camp_catalog(camp)
    if not cat:
        return 0, 0, 0
    folder = os.path.join(out_root, A.safe_name(camp))
    old = scan_old(folder)
    if not old:
        return 0, 0, len(cat)

    used = set()
    renamed = trashed = missing = 0
    for it in cat:
        new_name = API.course_filename(it, used=used)
        new_path = os.path.join(folder, new_name)
        title = it.get('title') or ''
        exp = it.get('duration') or 0

        if os.path.exists(new_path):
            continue                       # 已是新命名

        cands = old.get(A.safe_name(title)) or []
        if not cands:
            missing += 1
            continue

        good, rest = pick_by_duration(cands, exp)
        if good:
            renamed += 1
            log('  [改名] %s → %s' % (os.path.basename(good), new_name))
            if not dry:
                os.replace(good, new_path)
        else:
            trashed += len(cands)
            log('  [坏文件] %s / %s （%d 个）→ 移入 _trash_旧命名'
                % (camp, title, len(cands)))
            if not dry:
                os.makedirs(trash_dir, exist_ok=True)
                for p, _sz in cands:
                    shutil.move(p, os.path.join(trash_dir, os.path.basename(p)))
            continue
        # 该课多余的旧文件（并发 bug 的产物）→ 移到 trash
        for p in rest:
            trashed += 1
            log('  [多余] %s → 移入 _trash_旧命名' % os.path.basename(p))
            if not dry:
                os.makedirs(trash_dir, exist_ok=True)
                shutil.move(p, os.path.join(trash_dir, os.path.basename(p)))
    return renamed, trashed, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='Z:/太极营')
    ap.add_argument('--only', default=None)
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    trash = os.path.join(args.out, '_trash_旧命名')
    tot_r = tot_t = tot_m = 0
    for tab in ('正式营', '体验营'):
        for c in API.list_camps(tab):
            name = c['name']
            if args.only and args.only not in name:
                continue
            log('=== %s ===' % name)
            r, t, m = migrate_camp(name, args.out, trash, args.dry)
            log('  改名 %d，坏文件 %d，未下载 %d' % (r, t, m))
            tot_r += r
            tot_t += t
            tot_m += m
    log('')
    log('合计：改名 %d，坏文件 %d，未下载 %d' % (tot_r, tot_t, tot_m))
    if tot_t:
        log('坏文件已移到 %s（可自行删除）' % trash)


if __name__ == '__main__':
    main()
