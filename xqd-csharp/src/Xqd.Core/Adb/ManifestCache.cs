using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;

namespace Xqd.Core.Adb;

/// <summary>
/// fileId ↔ 课名 绑定与隐藏清单链接收集 —— 对照 xqd_app.py 的
/// _manifest_ids / play_and_capture / sweep_camp / collect_links_from_cache。
///
/// 已验证事实（docs/01 五节）：
///  · 播放一节课 → App 刷新隐藏清单 `.&lt;md5&gt;.hls` → 清单正文里的业务 fileId 就是这节课的 fileId。
///  · 用「清单 mtime 差分」精确定位当前播放的是哪一节课（轮询 0.35s）。
///  · 课名在进入课程列表页时就已知（见第四节），流程是「先收全课表 → 再逐节播放绑 fileId」，
///    不是播放后反推课名。
///  · 播放器按一次 BACK 回列表且滚动位置保留 → 直接继续下一节，不必重新定位。
/// </summary>
internal sealed class ManifestCache
{
    private readonly AdbDevice _dev;
    private readonly AdbState _state;

    public ManifestCache(AdbDevice dev, AdbState state)
    {
        _dev = dev;
        _state = state;
    }

    /// <summary>
    /// 点「去学习」→ 轮询隐藏清单刷新（mtime 差分）→ 返回 (fileId 列表, 变更清单名列表)。
    /// 对应 xqd_app.play_and_capture。
    /// </summary>
    public (List<string> ids, List<string> changed) PlayAndCapture(
        Card target,
        Dictionary<string, (string mtime, long size)> before,
        double timeout = 25.0)
    {
        _dev.Tap(target.Bx, target.By);
        var deadline = DateTime.UtcNow.AddSeconds(timeout);
        var changed = new List<string>();
        while (DateTime.UtcNow < deadline)
        {
            Thread.Sleep(350);                         // 0.35s 轮询
            var after = _dev.CacheState();
            changed = after.Keys
                .Where(f => f.StartsWith(".", StringComparison.Ordinal)
                            && f.IndexOf("hls", StringComparison.Ordinal) >= 0
                            && (!before.ContainsKey(f) || before[f].mtime != after[f].mtime))
                .ToList();
            if (changed.Count > 0) break;
        }

        var ids = new List<string>();
        foreach (var f in changed)
        {
            var txt = _dev.ReadManifest(f);         // _manifest_ids
            foreach (var i in _dev.BizIds(txt))
                if (!ids.Contains(i)) ids.Add(i);
        }
        return (ids, changed);
    }

    /// <summary>
    /// 逐节播放，把「课名 → fileId → 链接」写进 names.json / links.json。
    /// 对应 xqd_app.sweep_camp。返回 (播放节数, 新增映射数)。
    ///
    /// ★ by ≤ 320 的是吸顶悬浮按钮，跳过（docs/01 四节）。
    /// ★ 课名来自当前 dump 的卡片，不是播放后反推。
    /// </summary>
    public (int played, int newmap) SweepCamp(string camp, double timeout = 25.0,
                                              Action<int, int, string> progress = null)
    {
        var xml = _dev.OpenCourseList(camp);
        if (string.IsNullOrEmpty(xml)) return (0, 0);
        xml = _dev.ScrollTop(28);
        int total = Ui.ListTotal(xml);

        var done = new HashSet<(string title, string when)>();
        int played = 0, newmap = 0, stagnant = 0;

        while (true)
        {
            var cards = Ui.ListCards(xml);
            Card tgt = null;
            foreach (var c in cards)
            {
                if (string.IsNullOrEmpty(c.Title) || done.Contains((c.Title, c.When))) continue;
                if (c.Bx > 0 && c.By > 320) { tgt = c; break; }   // 跳过吸顶悬浮按钮
            }

            if (tgt == null)
            {
                var beforeWhens = cards.Select(c => c.When).ToList();
                _dev.ScrollDown(1.6);
                xml = _dev.UiDump();
                if (Ui.PageKind(xml) != "course_list") break;
                var afterWhens = Ui.ListCards(xml).Select(c => c.When).ToList();
                if (beforeWhens.SequenceEqual(afterWhens))
                {
                    stagnant++;
                    if (stagnant >= 3) break;
                }
                else stagnant = 0;
                continue;
            }

            done.Add((tgt.Title, tgt.When));
            played++;

            var before = _dev.CacheState();
            var (ids, changed) = PlayAndCapture(tgt, before, timeout);

            // 课名 → fileId（names.json）：fileId 已存在则不覆盖
            foreach (var bid in ids)
                if (_state.PutName(bid, tgt.Title, tgt.When, camp)) newmap++;

            // 清单 → 链接（links.json）：用清单里的第一个业务 fileId 作键
            foreach (var f in changed)
            {
                var txt = _dev.ReadManifest(f);
                var fids = _dev.BizIds(txt);
                var url = _dev.FirstUrl(txt);
                if (!string.IsNullOrEmpty(url) && fids.Count > 0)
                    _state.PutLink(fids[0], url, camp);
            }

            progress?.Invoke(played, total, tgt.Title);

            // 播放器按一次 BACK 回课程列表页，滚动位置保留（docs/01 二节）
            _dev.Back(1.5);
            xml = _dev.UiDump();
            if (Ui.PageKind(xml) != "course_list")
            {
                xml = _dev.OpenCourseList(camp);
                if (string.IsNullOrEmpty(xml)) break;
                xml = _dev.ScrollTop(28);
                done.Clear();
            }
        }

        _state.Save();
        return (played, newmap);
    }

    /// <summary>
    /// 从远端隐藏清单收集 {fileId: url}（不播放、不发网络请求）。
    /// 对应 xqd_app.collect_links_from_cache。
    /// </summary>
    public Dictionary<string, string> CollectLinksFromCache()
    {
        var outLinks = new Dictionary<string, string>(StringComparer.Ordinal);
        var st = _dev.CacheState();
        foreach (var f in st.Keys)
        {
            if (!(f.StartsWith(".", StringComparison.Ordinal) &&
                  f.IndexOf("hls", StringComparison.Ordinal) >= 0)) continue;
            var txt = _dev.ReadManifest(f);
            var url = _dev.FirstUrl(txt);
            if (string.IsNullOrEmpty(url)) continue;
            var ids = _dev.BizIds(txt);
            if (ids.Count > 0) outLinks[ids[0]] = url;
        }
        return outLinks;
    }

    /// <summary>把缓存里现成的链接合并进 links.json（ResolveAsync 的轻量兜底）。</summary>
    public void MergeLinksFromCache(string camp)
    {
        foreach (var kv in CollectLinksFromCache())
            _state.PutLink(kv.Key, kv.Value, camp);
        _state.Save();
    }
}
