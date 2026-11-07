# -*- coding: utf-8 -*-
"""下载历史持久化 —— 让「下载管理」表在**第二次打开工具**时还在。

背景（用户需求，2026-11-07）
----------------------------
    「添加记忆下载列表和下载进度的功能，既然已经实现断点续传，
      应当实现第二次打开工具时，保留用户曾经下载过的列表和下载进度，
      这样下载管理才有意义。」

两件要记住的东西
----------------
1. **下载列表**：曾经下载过哪些课（课名 + 营 + 成品路径 + 状态）。
2. **下载进度**：每节课下到哪了（已下字节 / 总字节 / 已下时长 / 总时长）。

为什么进度能跨会话恢复（**已实测**，见 docs/01-已验证事实.md）
    HLS 分片的**文件名**在两次不同会话之间**完全稳定**
    （实测 150/150 一致），只有 URL 上的签名参数 ``?sign=...`` 会变。
    所以只要把分片按文件名落盘，下次就能直接复用已下的那部分，
    真正做到「接着下」而不是「重下」。

本模块只管**记与读**（纯数据），不含任何界面逻辑。
"""

import json
import os
import time

# 分片缓存根目录（跨进程复用已下分片）
PARTS_DIR = os.path.join(os.path.expanduser('~'), '.xqd_tool', 'parts')

HISTORY_FILE = os.path.join(os.path.expanduser('~'), '.xqd_tool', 'history.json')

# ★ 测试隔离（见 xqd_gui 里的同名机制）——
#   不隔离的话测试会写坏用户真实的下载目录 / 历史记录。
if os.environ.get('XQD_TEST_HOME'):
    PARTS_DIR = os.path.join(os.environ['XQD_TEST_HOME'], 'parts')
    HISTORY_FILE = os.path.join(os.environ['XQD_TEST_HOME'], 'history.json')

# 保留的历史条数上限（防止文件无限膨胀）
MAX_HISTORY = 500


def load_history(path=None):
    """读历史。返回 {key: record}（key = 成品路径）。"""
    path = path or HISTORY_FILE
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}
    items = data.get('items')
    if not isinstance(items, list):
        return {}
    out = {}
    for rec in items:
        if isinstance(rec, dict) and rec.get('path'):
            out[rec['path']] = rec
    return out


def save_history(items, path=None):
    """写历史。items 是 record 列表。"""
    path = path or HISTORY_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        items = list(items)[-MAX_HISTORY:]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'version': 1, 'items': items}, f,
                      ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def make_record(path, title, camp='', state='', size=0,
                down=0, total=0, done_dur=0.0, total_dur=0.0,
                duration=0):
    """造一条历史记录。"""
    return {
        'path': path,
        'title': title,
        'camp': camp,
        'state': state,
        'size': int(size or 0),
        'down': int(down or 0),
        'total': int(total or 0),
        'done_dur': round(float(done_dur or 0.0), 2),
        'total_dur': round(float(total_dur or 0.0), 2),
        'duration': int(duration or 0),
        'ts': time.time(),
    }


def merge(history, rec):
    """把一条记录并进 history（按 path 去重，保留较新的）。

    返回 True 表示内容有变化（需要落盘）。
    """
    if not rec or not rec.get('path'):
        return False
    old = history.get(rec['path'])
    if old:
        # 已完成的记录不被后来的「排队中」覆盖
        if old.get('state') in ('已完成', '失败') \
                and rec.get('state') in ('排队中', '下载中', '解析中'):
            return False
        # 进度只前进，不后退
        for k in ('down', 'done_dur'):
            if float(rec.get(k) or 0) < float(old.get(k) or 0):
                rec[k] = old.get(k)
        if int(rec.get('total') or 0) < int(old.get('total') or 0):
            rec['total'] = old.get('total')
    history[rec['path']] = rec
    return True


def sort_items(history):
    """按时间倒序输出（新的在前）。"""
    items = list(history.values())
    items.sort(key=lambda r: r.get('ts') or 0, reverse=True)
    return items


# ── 分片缓存（跨进程续传）────────────────────────────────────

def parts_key(path):
    """由成品路径派生分片缓存目录名。

    ★ 用成品路径做 key：同一节课的缓存目录恒定，
      第二次打开工具、重新下载同一节时才能命中已下的分片。
    """
    import hashlib
    h = hashlib.md5(os.path.abspath(path).encode('utf-8')).hexdigest()
    return h[:16]


def parts_dir_for(path, root=None):
    """某一节课的分片缓存目录。"""
    root = root or PARTS_DIR
    return os.path.join(root, parts_key(path))


def parts_progress(seg_dir):
    """统计分片缓存里已下了多少。

    返回 (已下字节, 分片个数, 缓存总字节)。
    第三个值与第一个相同 —— 缓存里只有**已下好的**分片，
    总大小要从清单算（那在引擎侧），这里只报实数。
    """
    if not seg_dir or not os.path.isdir(seg_dir):
        return 0, 0, 0
    total = 0
    count = 0
    try:
        for fn in os.listdir(seg_dir):
            if fn.startswith('all.'):
                continue          # 拼接用的中间文件，不算
            p = os.path.join(seg_dir, fn)
            try:
                if os.path.isfile(p):
                    total += os.path.getsize(p)
                    count += 1
            except OSError:
                pass
    except OSError:
        pass
    return total, count, total


def purge_parts(path, root=None):
    """删掉某一节课的分片缓存目录（续传不再需要时）。

    返回删掉的字节数（目录不存在返回 0）。
    """
    root = root or PARTS_DIR
    d = parts_dir_for(path, root)
    if not os.path.isdir(d):
        return 0
    freed = 0
    try:
        for fn in os.listdir(d):
            p = os.path.join(d, fn)
            try:
                if os.path.isfile(p):
                    freed += os.path.getsize(p)
                    os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(d)
        except OSError:
            pass
    except OSError:
        pass
    return freed


def purge_all_parts(root=None):
    """清空整个分片缓存目录（返回释放的字节数）。

    ★ 用户流量昂贵 —— 分片缓存是「已下但还没转封装」的部分，
      清掉就等于要重下。所以只在用户明确要求时才调。
    """
    root = root or PARTS_DIR
    if not os.path.isdir(root):
        return 0
    freed = 0
    try:
        for name in os.listdir(root):
            d = os.path.join(root, name)
            if os.path.isdir(d):
                freed += purge_parts_dir(d)
    except OSError:
        pass
    return freed


def purge_parts_dir(d):
    """删一个分片目录里的所有文件（返回释放字节数）。"""
    freed = 0
    try:
        for fn in os.listdir(d):
            p = os.path.join(d, fn)
            try:
                if os.path.isfile(p):
                    freed += os.path.getsize(p)
                    os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(d)
        except OSError:
            pass
    except OSError:
        pass
    return freed


def purge_orphan_parts(history, root=None):
    """清理「孤儿」分片缓存 —— 返回 (清理目录数, 释放字节数)。

    ★ 只清**「已完成」**记录对应的分片目录：
      成功的课分片已无用（成品在下载目录里），残留纯属占磁盘。
      **「失败」和「未完成」的分片必须保留** —— 那是续传的本钱，
      清掉等于让用户重下（流量昂贵）。

    ★ 历史里没有对应记录的目录也清 —— 它们不可能被续传用上
      （续传靠的是历史里的成品路径 → parts_key）。
      但只清 parts/ 根目录下的一级子目录，不碰别的。
    """
    root = root or PARTS_DIR
    if not os.path.isdir(root):
        return 0, 0
    # 只有「已完成」的记录，其分片才可以清
    keep = set()
    for path, rec in (history or {}).items():
        st = (rec or {}).get('state') or ''
        if st != '已完成':
            keep.add(parts_key(path))
    n = 0
    freed = 0
    try:
        names = os.listdir(root)
    except OSError:
        return 0, 0
    for name in names:
        if name in keep:
            continue
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        b = purge_parts_dir(d)
        if b:
            freed += b
            n += 1
    return n, freed
