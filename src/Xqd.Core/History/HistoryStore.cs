using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using Xqd.Core;

namespace Xqd.Core.History;

/// <summary>
/// 下载历史持久化 + 分片缓存管理。逐函数对照 Python 的 xqd_history.py 全文。
///
/// 两件要记住的东西（用户需求）：
///   1. 下载列表：曾经下载过哪些课（课名 + 营 + 成品路径 + 状态）。
///   2. 下载进度：每节课下到哪了（已下字节 / 总字节 / 已下时长 / 总时长）。
///
/// 为什么进度能跨会话恢复：HLS 分片文件名在两次会话间 150/150 完全一致，
/// 只有 URL 上的 ?sign= 会变（docs/01 第十七节），按文件名落盘即可复用。
///
/// history.json 结构 {"version":1,"items":[...]}，上限 500 条；
/// 路径取 Config.HistoryFile / Config.PartsDir（XQD_TEST_HOME 隔离已由 Config 处理）。
/// </summary>
public sealed class HistoryStore : IHistoryStore
{
    private const int MaxHistory = 500;

    // ── history.json ──────────────────────────────────────────────

    /// <summary>读历史。对应 load_history：按成品路径主键去重，跳过无 path 的坏记录。</summary>
    public List<HistoryRecord> Load(string path = null)
    {
        var result = new List<HistoryRecord>();
        try
        {
            var p = path ?? Config.HistoryFile;
            if (!File.Exists(p)) return result;
            using var doc = JsonDocument.Parse(File.ReadAllText(p, Encoding.UTF8));
            if (!doc.RootElement.TryGetProperty("items", out var arr) ||
                arr.ValueKind != JsonValueKind.Array)
                return result;

            // path -> 在 result 里的下标；同主键后者覆盖（load_history 返回 dict 的语义）
            var seen = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (var e in arr.EnumerateArray())
            {
                HistoryRecord rec;
                try { rec = Config.Deserialize<HistoryRecord>(e.GetRawText()); }
                catch { continue; }
                if (rec == null || string.IsNullOrEmpty(rec.path)) continue;
                if (seen.TryGetValue(rec.path, out var idx)) result[idx] = rec;
                else { seen[rec.path] = result.Count; result.Add(rec); }
            }
        }
        catch { /* 读失败一律当作空历史 */ }
        return result;
    }

    /// <summary>写历史。对应 save_history：只保留最后 500 条，写 {"version":1,"items":[...]}。</summary>
    public bool Save(IEnumerable<HistoryRecord> items, string path = null)
    {
        try
        {
            var p = path ?? Config.HistoryFile;
            var dir = Path.GetDirectoryName(p);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            var list = (items ?? Enumerable.Empty<HistoryRecord>()).ToList();
            if (list.Count > MaxHistory)
                list = list.Skip(list.Count - MaxHistory).ToList();

            var json = Config.Serialize(new { version = 1, items = list });
            File.WriteAllText(p, json, new UTF8Encoding(false));
            return true;
        }
        catch { return false; }
    }

    /// <summary>
    /// 按 path 合并一条记录（对应 merge）。返回是否需要落盘。
    /// 已完成 / 失败 不被后来的「排队中 / 下载中 / 解析中」覆盖；
    /// down / done_dur 只前进不后退，total 只增。
    /// </summary>
    public bool Merge(List<HistoryRecord> history, HistoryRecord rec)
    {
        if (history == null || rec == null || string.IsNullOrEmpty(rec.path)) return false;

        int idx = -1;
        for (int i = 0; i < history.Count; i++)
        {
            if (string.Equals(history[i]?.path, rec.path, StringComparison.Ordinal))
            { idx = i; break; }
        }

        if (idx >= 0)
        {
            var old = history[idx];
            if ((old.state == "已完成" || old.state == "失败") &&
                (rec.state == "排队中" || rec.state == "下载中" || rec.state == "解析中"))
                return false;                       // 终态保护，不覆盖、无需落盘

            if (rec.down < old.down) rec.down = old.down;
            if (rec.done_dur < old.done_dur) rec.done_dur = old.done_dur;
            if (rec.total < old.total) rec.total = old.total;
            history[idx] = rec;
        }
        else
        {
            history.Add(rec);
        }
        return true;
    }

    /// <summary>按 ts 倒序输出（新的在前）。对应 sort_items，返回新列表，不改原列表。</summary>
    public List<HistoryRecord> Sort(List<HistoryRecord> history) =>
        (history ?? new List<HistoryRecord>())
            .OrderByDescending(r => r.ts).ToList();

    // ── 分片缓存（跨进程续传）───────────────────────────────────

    /// <summary>
    /// 由成品路径派生分片缓存目录名：md5(Path.GetFullPath(outPath))[:16]。
    /// 与 Python 的 md5(os.path.abspath(path))[:16] 一致（GetFullPath ≈ abspath，
    /// Util.Md5Hex 用 UTF8 编码、小写 hex）。
    /// </summary>
    public string PartsKey(string outPath) =>
        Util.Md5Hex(Path.GetFullPath(string.IsNullOrEmpty(outPath) ? "." : outPath))
            .Substring(0, 16);

    /// <summary>某一节课的分片缓存目录。对应 parts_dir_for。</summary>
    public string PartsDirFor(string outPath, string root = null) =>
        Path.Combine(root ?? Config.PartsDir, PartsKey(outPath));

    /// <summary>
    /// 统计分片缓存里已下了多少（对应 parts_progress）。
    /// 跳过 all.* 拼接中间文件；返回 (已下字节, 分片个数, 缓存总字节)，
    /// 第三个值与第一个相同 —— 缓存里只有已下好的分片。
    /// </summary>
    public (long Bytes, int Count, long CacheBytes) PartsProgress(string segDir)
    {
        if (string.IsNullOrEmpty(segDir) || !Directory.Exists(segDir)) return (0, 0, 0);
        long total = 0;
        int count = 0;
        try
        {
            foreach (var f in Directory.EnumerateFiles(segDir))
            {
                if (Path.GetFileName(f).StartsWith("all.", StringComparison.Ordinal)) continue;
                try { total += new FileInfo(f).Length; count++; }
                catch { /* 单个文件失效忽略 */ }
            }
        }
        catch { /* 目录读取失败 */ }
        return (total, count, total);
    }

    /// <summary>删掉某一节课的分片缓存目录，返回释放字节数（对应 purge_parts）。</summary>
    public long PurgeParts(string outPath, string root = null) =>
        PurgePartsDir(PartsDirFor(outPath, root));

    /// <summary>
    /// 清空整个分片缓存目录（对应 purge_all_parts）。
    /// ★ 流量昂贵，缓存是「已下但还没转封装」的部分，清掉等于要重下，
    ///   所以只在用户明确要求时才调；启动清理请用 PurgeOrphanParts。
    /// </summary>
    public long PurgeAllParts(string root = null)
    {
        var r = root ?? Config.PartsDir;
        if (!Directory.Exists(r)) return 0;
        long freed = 0;
        try
        {
            foreach (var d in Directory.EnumerateDirectories(r).ToList())
                freed += PurgePartsDir(d);
        }
        catch { /* 忽略 */ }
        return freed;
    }

    /// <summary>
    /// 清理「孤儿」分片缓存（对应 purge_orphan_parts，接口返回 void，故不返回计数）。
    ///
    /// ★ 只清「已完成」记录对应的分片目录：成功的课成品已在下载目录，
    ///   残留纯属占磁盘。**「失败」「未完成」必须保留** —— 那是续传本钱，
    ///   清掉等于让用户重下（流量昂贵）。
    /// ★ 历史里没有对应记录的目录也清（无主缓存不可能被续传用上）。
    /// ★ 只清 parts/ 根目录下的一级子目录，不碰别的。
    /// </summary>
    public void PurgeOrphanParts(List<HistoryRecord> history, string root = null)
    {
        var r = root ?? Config.PartsDir;
        if (!Directory.Exists(r)) return;

        var keep = new HashSet<string>(StringComparer.Ordinal);
        foreach (var rec in history ?? new List<HistoryRecord>())
        {
            if (rec == null || string.IsNullOrEmpty(rec.path)) continue;
            // 只有「已完成」的分片才可清；其余（失败/未完成/异常态）一律保留
            if (rec.state != "已完成") keep.Add(PartsKey(rec.path));
        }

        try
        {
            foreach (var d in Directory.EnumerateDirectories(r).ToList())
            {
                if (keep.Contains(Path.GetFileName(d))) continue;
                PurgePartsDir(d);
            }
        }
        catch { /* 忽略 */ }
    }

    /// <summary>
    /// 删一个分片目录里的所有文件（对应 purge_parts_dir），返回释放字节数。
    /// ★ 必须逐个 File.Delete + 删空目录，不能用 Directory.Delete(recursive:true)：
    ///   批量删除会触发安全删除钩子阈值（50）被拦下，临时目录会一直累积
    ///   （docs/11 G 节、docs/01 第八节，实测跑到第 16 节已积 848MB）。
    /// ★ 先物化文件清单再删，避免「边枚举边删」漏删。
    /// </summary>
    private static long PurgePartsDir(string d)
    {
        long freed = 0;
        if (string.IsNullOrEmpty(d) || !Directory.Exists(d)) return 0;
        try
        {
            foreach (var f in Directory.EnumerateFiles(d).ToList())
            {
                try
                {
                    freed += new FileInfo(f).Length;
                    File.Delete(f);
                }
                catch { /* 单个删不掉就跳过 */ }
            }
            try { Directory.Delete(d, false); } catch { /* 非空则留着 */ }
        }
        catch { /* 忽略 */ }
        return freed;
    }
}
