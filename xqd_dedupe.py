# -*- coding: utf-8 -*-
"""已下载检测 —— 决定「这节课是不是已经下过了」。

比较维度的选择（本项目的硬约束：网络极不稳定、流量昂贵）
------------------------------------------------------------
我们要在「下载前」判断某节课是否已有成品，能用的信号只有三类：

==============  ========  ========  ==================================
信号            成本      准确性    结论
==============  ========  ========  ==================================
**文件名**      零        中        **用**。序号+课名+日期 唯一标识一节课
**时长**        ~100ms    高        **用**。ffprobe 一次，证明完整且是同一节
**文件大小**    零        低        只作下限门槛（>10KB），不作判据
**哈希**        全量读盘  极高      **不用**。几十万 MB 全读一遍太慢
**联网查大小**  一次请求  高        **不用**。违背「少请求」约束，且 CDN 每次
                                    签名不同、Content-Length 未必稳定
==============  ========  ========  ==================================

最终判据
--------
1. 用**文件名主键**（去掉扩展名的「序号.课名.日期」）在目标营目录里找候选；
2. 候选存在且大小 > 10KB；
3. ffprobe 一次拿时长，与课表标称时长比对（容差 max(3s, 1%)）；
   课表没标时长（AUDIO 里有一部分 duration=0）时，**只做第 1、2 步**。

效率
----
绝大多数课程**没下过** → 目录里根本没有同名文件，第 1 步就否掉，
一次 ffprobe 都不会发生。只有真正已下过的课才会付 ffprobe 的钱。
"""

import json
import os
import re

# 成品最小合理大小：低于此视为残缺/空文件
MIN_SIZE = 10 * 1024

# 允许的成品扩展名
MEDIA_EXTS = ('.mp4', '.mp3', '.m4a', '.aac', '.mov', '.mkv', '.webm')

# sidecar 索引文件名（缓存 ffprobe 结果，避免重复探测）
INDEX_NAME = '.xqd_index.json'


def stem_of(path_or_name):
    """去掉扩展名，得到「文件名主键」。"""
    return os.path.splitext(os.path.basename(path_or_name))[0]


def list_media(folder):
    """列出目录里的成品文件。

    返回 {stem: (path, size)}。同 stem 多个文件时取**最新修改的**。
    """
    out = {}
    if not folder or not os.path.isdir(folder):
        return out
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for fn in names:
        if fn.startswith('.'):
            continue
        ext = os.path.splitext(fn)[1].lower()
        if ext not in MEDIA_EXTS:
            continue
        p = os.path.join(folder, fn)
        try:
            st = os.stat(p)
        except OSError:
            continue
        if not os.path.isfile(p):
            continue
        key = stem_of(fn)
        prev = out.get(key)
        if prev is None or st.st_mtime > prev[2]:
            out[key] = (p, st.st_size, st.st_mtime)
    return {k: (v[0], v[1]) for k, v in out.items()}


def legacy_camp_folders(root, camp_name, camp_count=None):
    """推导**历史目录名**（旧版工具用错名字时留下的）。

    背景：旧版把 Camp **对象**传进 safe_name()，被 str() 成了
    ``"<Camp 道德经诵读 (27节)>"``，清洗后变成目录名
    ``_Camp 道德经诵读 (27节)_``。

    现在新工具用 camp.name（目录名 ``道德经诵读``），
    但旧批处理已经把 77 个成品下到了旧目录里 —— 检测时必须一起看，
    否则会重复下载（流量昂贵，用户明确要求省流量）。

    返回历史目录名列表（可能为空）。
    """
    out = []
    if camp_count is not None:
        legacy = '_Camp %s (%d节)_' % (camp_name, camp_count)
        p = os.path.join(root, legacy)
        if os.path.isdir(p):
            out.append(p)
    # 不确定节数时，扫一遍根目录找同前缀的
    if not out and root and os.path.isdir(root):
        try:
            for fn in os.listdir(root):
                if fn.startswith('_Camp %s (' % camp_name) and \
                        fn.endswith(')_') and os.path.isdir(
                            os.path.join(root, fn)):
                    out.append(os.path.join(root, fn))
        except OSError:
            pass
    return out


class ExistingChecker(object):
    """按目录缓存成品清单 + ffprobe 时长，判定某节课是否已下过。

    用法::

        ck = ExistingChecker(out_root)
        state = ck.check(camp_folder, lesson_stem, expect_duration)
        # state.status: 'missing' | 'ok' | 'broken'
    """

    def __init__(self, out_root):
        self.out_root = out_root
        self._index = {}        # path -> {'dur': float, 'size': int, 'mtime': float}
        self._dirs = {}         # folder -> {stem: (path, size)}
        self._scan_time = {}    # folder -> ts

    # ── 目录扫描 ──
    def _scan(self, folder):
        """列出目录里的成品（带短 TTL 缓存）。

        ⚠️ 缓存不能作为「文件是否存在」的判据 —— 刚下载完的文件若被
        TTL 缓存挡住，会被误判成「没下过」而重复下载。
        所以 check() 里会先 stat 目标文件确认存在，再走时长校验。
        """
        now = _now()
        ts = self._scan_time.get(folder, 0)
        cached = self._dirs.get(folder)
        if cached is not None and now - ts < 5.0:
            return cached
        result = list_media(folder)
        self._dirs[folder] = result
        self._scan_time[folder] = now
        return result

    def _find_candidate(self, folder, stem):
        """兼容旧接口：找一个与 stem 匹配、且**磁盘上确实存在**的成品。

        已下载判定请用 check_group()（能区分 ok / broken 并处理 -N 后缀）。
        """
        group = self.find_group(folder, stem)
        if not group:
            return None
        group.sort(key=lambda x: x[1], reverse=True)
        return group[0]

    @staticmethod
    def _stem_variants(stem):
        """主键的候选形态：本体 + ``-1`` … ``-9`` 重名后缀。"""
        out = [stem]
        for k in range(1, 10):
            out.append('%s-%d' % (stem, k))
        return out

    def find_group(self, folder, stem):
        """找出该主键下的**所有**候选文件（含 ``-N`` 重名后缀）。

        返回 [(path, size)]，按文件名排序。

        为什么需要「整组」而不是单个：旧批处理曾对同一节课重复下载，
        产生 ``xxx.mp4`` 与 ``xxx-1.mp4`` 两个文件。判断「这节课是不是
        已经下好了」必须看整组 —— 只要组里有一个**完整**的就跳过；
        全都不完整才需要重下（并清理掉残件）。

        ⚠️ 必须**一次 listdir + 内存匹配**，不能对每个候选名逐个
        ``os.path.isfile``：候选形态是「10 个 stem 变体 × 7 个扩展名」
        = 70 次路径探测，在 SMB 网络盘上每次都是一次网络往返，
        单节就要好几秒，一营 70 节能卡十几分钟（实测教训）。
        """
        out = []
        if not folder or not os.path.isdir(folder):
            return out
        try:
            names = os.listdir(folder)
        except OSError:
            return out
        want = set(self._stem_variants(stem))
        for fn in names:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in MEDIA_EXTS:
                continue
            base = os.path.splitext(fn)[0]
            if base not in want:
                continue
            p = os.path.join(folder, fn)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            out.append((p, size))
        out.sort()
        return out

    def _classify(self, path, size, expect_duration=0):
        """判断**单个文件**是否完整可信。返回 (ok: bool, reason: str)。"""
        if size < MIN_SIZE:
            return False, '文件过小（%d 字节），疑似残缺' % size
        if expect_duration and expect_duration > 0:
            dur = self._duration(path)
            if dur <= 0:
                return False, '无法解析时长，疑似损坏'
            tol = max(3.0, expect_duration * 0.01)
            if abs(dur - expect_duration) > tol:
                return False, ('时长不符（%.1fs vs 期望 %.1fs）'
                               % (dur, expect_duration))
            return True, '完整（%.1fs）' % dur
        return True, '完整'

    def check_group(self, folder, stem, expect_duration=0, alt_folders=None):
        """整组判定 —— 决定「跳过」还是「覆盖重下」。

        返回 dict:
            status  'ok'      组里有完整成品 → **跳过下载**
                    'broken'  组里只有残缺文件 → **覆盖重下**
                    'missing' 一个文件都没有 → 正常下载
            files   [(path, size, ok, reason)]
            path    完整成品的路径（status == 'ok' 时有值）
            reason  人类可读说明
        """
        candidates = [folder]
        for alt in (alt_folders or []):
            if alt and alt not in candidates:
                candidates.append(alt)

        group = []
        for fdir in candidates:
            group.extend(self.find_group(fdir, stem))
        if not group:
            return {'status': 'missing', 'files': [], 'path': '',
                    'size': 0, 'duration': 0.0, 'reason': '未下载'}

        best = None
        classified = []
        for path, size in group:
            ok, reason = self._classify(path, size, expect_duration)
            classified.append((path, size, ok, reason))
            if ok and (best is None or size > best[1]):
                best = (path, size)

        if best is not None:
            dur = self._duration(best[0]) if expect_duration else 0.0
            return {'status': 'ok', 'files': classified, 'path': best[0],
                    'size': best[1], 'duration': dur,
                    'reason': '已存在且完整'}

        bad = [g for g in classified if not g[2]]
        return {'status': 'broken', 'files': classified, 'path': '',
                'size': bad[0][1] if bad else 0, 'duration': 0.0,
                'reason': (bad[0][3] if bad else '文件残缺')}

    def purge_broken(self, folder, stem, expect_duration=0, alt_folders=None):
        """删除该主键下**不完整**的文件，返回被删的路径列表。

        只删「判定为残缺」的文件（过小 / 无法解析 / 时长不符）。
        只要组里存在一个完整文件，就一个都不删（那是别的课或别的版本，
        贸然删会丢用户数据）。
        """
        st = self.check_group(folder, stem, expect_duration,
                              alt_folders=alt_folders)
        if st['status'] != 'broken':
            return []
        removed = []
        for path, _size, _ok, _reason in st['files']:
            try:
                os.remove(path)
                removed.append(path)
            except OSError:
                pass
        if removed:
            self.invalidate()
            for p in removed:
                self._index.pop(p, None)
        return removed

    def invalidate(self, folder=None):
        """下载完成后让缓存失效（下次重新扫目录）。"""
        if folder:
            self._dirs.pop(folder, None)
            self._scan_time.pop(folder, None)
        else:
            self._dirs.clear()
            self._scan_time.clear()

    # ── 时长探测（带缓存）──
    def _duration(self, path):
        st = None
        try:
            st = os.stat(path)
        except OSError:
            return 0.0
        key = path
        hit = self._index.get(key)
        if hit and hit['size'] == st.st_size and hit['mtime'] == st.st_mtime:
            return hit['dur']
        from xqd_engine import probe_duration
        dur = probe_duration(path)
        self._index[key] = {'dur': dur, 'size': st.st_size,
                            'mtime': st.st_mtime}
        return dur

    # ── sidecar 索引（可选，用于跨会话记录）──
    def save_index(self):
        """把时长探测结果写到下载根目录的 sidecar 文件。

        作用：下次启动可以直接复用已知时长，不必重新 ffprobe。
        失败静默（这是优化，不是必需功能）。
        """
        if not self.out_root:
            return
        try:
            os.makedirs(self.out_root, exist_ok=True)
            path = os.path.join(self.out_root, INDEX_NAME)
            payload = {
                'version': 1,
                'updated': _now(),
                'files': {
                    k: {'dur': round(v['dur'], 2), 'size': v['size'],
                        'mtime': v['mtime']}
                    for k, v in self._index.items()
                },
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception:
            pass

    def load_index(self):
        """载入 sidecar 索引（若有）。"""
        if not self.out_root:
            return
        path = os.path.join(self.out_root, INDEX_NAME)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception:
            return
        for k, v in (payload.get('files') or {}).items():
            try:
                self._index[k] = {'dur': float(v.get('dur') or 0),
                                  'size': int(v.get('size') or 0),
                                  'mtime': float(v.get('mtime') or 0)}
            except Exception:
                continue


def _now():
    import time
    return time.time()
