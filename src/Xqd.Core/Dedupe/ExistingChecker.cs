using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using Xqd.Core;

namespace Xqd.Core.Dedupe;

/// <summary>
/// 已下载检测 —— 决定「这节课是不是已经下过了」。
/// 逐函数对照 Python 的 xqd_dedupe.py 全文（stem_of / list_media /
/// legacy_camp_folders / find_group / _classify / check_group / _duration /
/// save_index / load_index / invalidate）。
///
/// 判据顺序（docs/01 〇之四，硬约束）：
///   ① 按文件名主键（去扩展名的「序号.课名.日期」）在营目录里找候选
///   ② 候选存在且大小 &gt; 10KB
///   ③ ffprobe 取时长与课表标称比对（容差 max(3s, 1%)）
///   课表 duration=0 时只做 ①②。
///   不用哈希（几十万 MB 全读太慢）、不联网查 Content-Length（违背少请求约束）。
///
/// ★ 效率：目录扫描一次 listdir 建索引再内存匹配（SMB 网络盘上逐个 exists
///   几百个候选会慢到 8 分钟，docs/11 G 节）；同 stem 多文件取最新修改的。
/// ★ 目录快照缓存不能当判据：命中后一律先 stat 磁盘确认存在与最新大小，
///   且「命中旧快照却全 miss」时强制重新 listdir，防止刚下载完的文件被漏检。
/// </summary>
public sealed class ExistingChecker : IExistingChecker
{
    private const long MinSize = 10 * 1024;              // 成品最小合理大小
    private const string IndexName = ".xqd_index.json";  // sidecar 索引文件名
    private const double ScanTtlSeconds = 5.0;          // 目录快照 TTL（对齐 Python _scan）

    private static readonly HashSet<string> MediaExts =
        new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        { ".mp4", ".mp3", ".m4a", ".aac", ".mov", ".mkv", ".webm" };

    private readonly string _outRoot;
    // 目录快照：folder -> (stem -> 最新文件)；带 TTL，仅作候选来源，绝不当存在判据
    private readonly Dictionary<string, Snapshot> _dirs =
        new Dictionary<string, Snapshot>(StringComparer.OrdinalIgnoreCase);
    // 旧营目录推导结果缓存：key = legacyRoot|campName
    private readonly Dictionary<string, List<string>> _legacyCache =
        new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
    // ffprobe 结果：path -> (dur, size, mtime)
    private readonly Dictionary<string, IdxEntry> _index =
        new Dictionary<string, IdxEntry>(StringComparer.OrdinalIgnoreCase);

    private string _ffprobe;   // 解析一次 ffprobe.exe 路径后缓存

    public ExistingChecker(string outRoot)
    {
        _outRoot = outRoot ?? "";
        LoadIndex();            // 载入 sidecar，跨会话复用已知时长
    }

    // ── 对外契约 ─────────────────────────────────────────────────

    /// <summary>
    /// 按文件名主键 + 10KB 门槛 + ffprobe 时长判定。
    /// 正常目录命中 → "ok"；只有旧营目录命中 → "legacy_ok"；
    /// 有候选但全残缺 → "broken"；一个都没有 → "missing"。
    /// </summary>
    public ExistingState Check(string campFolder, string stem, double expectDuration)
    {
        var st = new ExistingState();   // 默认 missing，全字段为空/0
        if (string.IsNullOrEmpty(stem)) return st;

        var mainDir = ResolveCampDir(campFolder);
        var campName = Path.GetFileName(
            mainDir.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
        var parent = Path.GetDirectoryName(mainDir);
        var legacyRoot = string.IsNullOrEmpty(parent) ? _outRoot : parent;

        // 候选目录 = 正常营目录 + 所有旧营目录（一次 listdir 根 + 缓存）
        var dirs = new List<string> { mainDir };
        foreach (var alt in LegacyFolders(legacyRoot, campName))
            if (!dirs.Contains(alt, StringComparer.OrdinalIgnoreCase)) dirs.Add(alt);

        var want = StemVariants(stem);   // 本体 + -1 … -9 重名后缀

        bool usedCache;
        var group = CollectGroup(dirs, mainDir, want, false, out usedCache);
        // ★ 防 TTL 漏新文件：命中旧快照却一个都没匹配到 → 强制重新 listdir 再查一次
        if (group.Count == 0 && usedCache)
            group = CollectGroup(dirs, mainDir, want, true, out _);

        group.Sort((a, b) => string.CompareOrdinal(a.Path, b.Path));  // 对齐 find_group 的 out.sort()

        Cand best = null;
        double bestDur = 0;
        foreach (var c in group)
        {
            double dur;
            if (!Classify(c.Path, c.Size, expectDuration, out dur)) continue;
            if (best == null || c.Size > best.Size) { best = c; bestDur = dur; }
        }

        if (best != null)
        {
            st.Status = best.IsLegacy ? "legacy_ok" : "ok";
            st.Path = best.Path;
            st.Size = best.Size;
            st.Duration = expectDuration > 0 ? bestDur : 0.0;
            return st;
        }
        if (group.Count > 0)
        {
            // 组里只有残缺文件 → 覆盖重下；path 留空（对齐 check_group 的 broken）
            st.Status = "broken";
            st.Size = group[0].Size;
            return st;
        }
        return st;
    }

    /// <summary>下载完成后让目录缓存失效（对齐 Python invalidate）。空参数清全部。</summary>
    public void Invalidate(string campFolder)
    {
        if (string.IsNullOrEmpty(campFolder))
        {
            _dirs.Clear();
            _legacyCache.Clear();
            return;
        }
        _dirs.Remove(ResolveCampDir(campFolder));
        _legacyCache.Clear();   // 旧目录清单也可能变，一并重建
    }

    // ── 目录扫描：一次 listdir 建索引 ───────────────────────────

    private sealed class Snapshot
    {
        public Dictionary<string, Entry> Index;
        public double TakenAt;
    }

    private sealed class Entry
    {
        public string Path;
        public long Size;
        public double MTime;    // 同 stem 取最新修改的依据
    }

    private sealed class Cand
    {
        public string Path;
        public long Size;
        public bool IsLegacy;   // 是否来自旧营目录（决定 ok / legacy_ok）
    }

    private sealed class IdxEntry
    {
        public double Dur;
        public long Size;
        public double MTime;
    }

    private static double Now() =>
        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;

    /// <summary>
    /// 一次 listdir 建索引（对应 list_media / find_group）：跳过隐藏文件、只留媒体扩展名，
    /// 同 stem 多文件取 mtime 最新的。**绝不对每个候选名逐个 exists**。
    /// </summary>
    private static Dictionary<string, Entry> BuildIndex(string folder)
    {
        var index = new Dictionary<string, Entry>(StringComparer.Ordinal);
        if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder)) return index;
        try
        {
            foreach (var f in Directory.EnumerateFiles(folder))
            {
                var fn = Path.GetFileName(f);
                if (fn.Length == 0 || fn[0] == '.') continue;        // 跳过 sidecar 等隐藏文件
                if (!MediaExts.Contains(Path.GetExtension(fn))) continue;
                var stem = Path.GetFileNameWithoutExtension(fn);     // = stem_of
                try
                {
                    var fi = new FileInfo(f);
                    var mtime = new DateTimeOffset(fi.LastWriteTimeUtc).ToUnixTimeMilliseconds() / 1000.0;
                    if (!index.TryGetValue(stem, out var prev) || mtime > prev.MTime)
                        index[stem] = new Entry { Path = f, Size = fi.Length, MTime = mtime };
                }
                catch { /* 单个文件 stat 失败忽略 */ }
            }
        }
        catch { /* 目录读取失败返回空索引 */ }
        return index;
    }

    /// <summary>带 TTL 的目录快照（对应 _scan）。forceFresh=true 时忽略缓存重新 listdir。</summary>
    private Dictionary<string, Entry> Scan(string folder, bool forceFresh, out bool fromCache)
    {
        fromCache = false;
        if (!forceFresh &&
            _dirs.TryGetValue(folder, out var snap) && Now() - snap.TakenAt < ScanTtlSeconds)
        {
            fromCache = true;
            return snap.Index;
        }
        var index = BuildIndex(folder);
        _dirs[folder] = new Snapshot { Index = index, TakenAt = Now() };
        return index;
    }

    /// <summary>主键的候选形态：本体 + -1 … -9 重名后缀（对应 _stem_variants）。</summary>
    private static HashSet<string> StemVariants(string stem)
    {
        var s = new HashSet<string>(StringComparer.Ordinal) { stem };
        for (int k = 1; k <= 9; k++)
            s.Add(stem + "-" + k.ToString(CultureInfo.InvariantCulture));
        return s;
    }

    /// <summary>
    /// 收集所有候选目录下、匹配主键的成品（对应 check_group 汇总 find_group 结果）。
    /// ★ 命中索引后必须先 stat 磁盘确认存在并取最新大小 —— 目录快照缓存不能当判据。
    /// </summary>
    private List<Cand> CollectGroup(List<string> dirs, string mainDir,
                                    HashSet<string> want, bool forceFresh,
                                    out bool usedCache)
    {
        var group = new List<Cand>();
        usedCache = false;
        foreach (var d in dirs)
        {
            bool fromCache;
            var index = Scan(d, forceFresh, out fromCache);
            usedCache |= fromCache;
            foreach (var kv in index)
            {
                if (!want.Contains(kv.Key)) continue;         // 内存匹配，不做路径探测
                try
                {
                    if (!File.Exists(kv.Value.Path)) continue;   // ★ 先 stat 确认磁盘上确实存在
                    var fi = new FileInfo(kv.Value.Path);
                    group.Add(new Cand
                    {
                        Path = kv.Value.Path,
                        Size = fi.Length,
                        IsLegacy = !string.Equals(d, mainDir, StringComparison.OrdinalIgnoreCase),
                    });
                }
                catch { /* 单个文件失效忽略 */ }
            }
        }
        return group;
    }

    /// <summary>
    /// 推导旧营目录名（对应 legacy_camp_folders 的「不确定节数」分支）。
    /// 旧版把 Camp 对象传进 safe_name()，被 str() 成 "&lt;Camp 营名 (N节)&gt;"，
    /// 清洗后目录名形如 "_Camp 营名 (N节)_"；77 个成品在旧目录里，漏检会重复下载。
    /// 一次 listdir 根目录 + 前缀/后缀匹配 + 结果缓存。
    /// </summary>
    private List<string> LegacyFolders(string legacyRoot, string campName)
    {
        var key = (legacyRoot ?? "") + "|" + campName;
        if (_legacyCache.TryGetValue(key, out var cached)) return cached;

        var outList = new List<string>();
        if (!string.IsNullOrEmpty(legacyRoot) && Directory.Exists(legacyRoot))
        {
            var prefix = "_Camp " + campName + " (";
            try
            {
                foreach (var d in Directory.EnumerateDirectories(legacyRoot))
                {
                    var name = Path.GetFileName(d);
                    if (name.StartsWith(prefix, StringComparison.Ordinal) &&
                        name.EndsWith(")_", StringComparison.Ordinal))
                        outList.Add(d);
                }
            }
            catch { /* 根目录读失败当没有旧目录 */ }
        }
        outList.Sort(StringComparer.Ordinal);
        _legacyCache[key] = outList;
        return outList;
    }

    /// <summary>
    /// campFolder 既可能是营目录名（相对 outRoot，如 Naming.CampFolder 的返回值），
    /// 也可能是完整路径，两种都兼容；统一解析成绝对路径作为缓存 key 与扫描目标。
    /// </summary>
    private string ResolveCampDir(string campFolder)
    {
        var cf = campFolder ?? "";
        bool looksLikePath = Path.IsPathRooted(cf) ||
            cf.IndexOf(Path.DirectorySeparatorChar) >= 0 ||
            cf.IndexOf(Path.AltDirectorySeparatorChar) >= 0;
        try
        {
            return looksLikePath
                ? Path.GetFullPath(cf)
                : Path.GetFullPath(Path.Combine(_outRoot, cf));
        }
        catch { return cf; }
    }

    // ── 单文件完整性与时长 ─────────────────────────────────────

    /// <summary>判断单个文件是否完整可信（对应 _classify）。</summary>
    private bool Classify(string path, long size, double expect, out double dur)
    {
        dur = 0;
        if (size < MinSize) return false;                 // ② 过低视为残缺
        if (expect > 0)                                    // ③ 课表标称了时长才 ffprobe
        {
            dur = ProbeDuration(path);
            if (dur <= 0) return false;                    // 无法解析 → 疑似损坏
            var tol = Math.Max(3.0, expect * 0.01);       // 容差 max(3s, 1%)
            if (Math.Abs(dur - expect) > tol) return false;
        }
        return true;                                       // duration=0 → 只做 ①②
    }

    /// <summary>
    /// ffprobe 取时长（带缓存，对应 _duration）：先 stat，size/mtime 未变则复用；
    /// 变了才重新探测并把结果写进 sidecar 索引（跨会话复用）。失败返回 0。
    /// </summary>
    private double ProbeDuration(string path)
    {
        long size = 0;
        double mtime = 0;
        try
        {
            if (!File.Exists(path)) return 0.0;
            var fi = new FileInfo(path);
            size = fi.Length;
            mtime = new DateTimeOffset(fi.LastWriteTimeUtc).ToUnixTimeMilliseconds() / 1000.0;
        }
        catch { return 0.0; }

        if (_index.TryGetValue(path, out var hit) &&
            hit.Size == size && hit.MTime == mtime)
            return hit.Dur;

        var dur = FfprobeDuration(path);
        _index[path] = new IdxEntry { Dur = dur, Size = size, MTime = mtime };
        SaveIndex();     // 优化，失败静默
        return dur;
    }

    /// <summary>调 ffprobe（子进程走 Xqd.Core.Proc，无黑框）。命令对齐 xqd_engine.probe_duration。</summary>
    private double FfprobeDuration(string path)
    {
        try
        {
            var r = Proc.Run(FfprobeExe(), new[]
            {
                "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", path,
            }, 180000);
            if (!r.Ok) return 0.0;
            if (double.TryParse((r.Out ?? "").Trim(), NumberStyles.Any,
                                CultureInfo.InvariantCulture, out var d) && d > 0)
                return d;
        }
        catch { /* 探测失败 → 0 */ }
        return 0.0;
    }

    /// <summary>定位 ffprobe.exe：**工具自装目录**（v1.6.3 自动安装的）
    ///   → PATH（对齐 shutil.which）→ 固定回退目录 → 交给系统。</summary>
    private string FfprobeExe()
    {
        if (_ffprobe != null) return _ffprobe;
        // ★ v1.6.3：工具自装目录优先
        string self = Path.Combine(Setup.DependencyCheck.ToolFfmpegDir, "ffprobe.exe");
        if (File.Exists(self)) { _ffprobe = self; return self; }
        string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var dir in pathEnv.Split(Path.PathSeparator))
        {
            if (string.IsNullOrEmpty(dir)) continue;
            try
            {
                var p = Path.Combine(dir, "ffprobe.exe");
                if (File.Exists(p)) { _ffprobe = p; return p; }
            }
            catch { /* 忽略非法 PATH 段 */ }
        }
        foreach (var dir in new[]
        {
            @"D:\user\chisenin\download\Programs\ffmpeg-8.0.1-essentials_build\bin",
            @"C:\LEL\LEL-Downloader\Source\ffmpeg",
        })
        {
            var p = Path.Combine(dir, "ffprobe.exe");
            if (File.Exists(p)) { _ffprobe = p; return p; }
        }
        _ffprobe = "ffprobe";
        return _ffprobe;
    }

    // ── sidecar 索引（对应 load_index / save_index）─────────────

    private string IndexPath => Path.Combine(_outRoot, IndexName);

    private void LoadIndex()
    {
        if (string.IsNullOrEmpty(_outRoot)) return;
        try
        {
            if (!File.Exists(IndexPath)) return;
            using var doc = JsonDocument.Parse(File.ReadAllText(IndexPath, Encoding.UTF8));
            if (!doc.RootElement.TryGetProperty("files", out var files) ||
                files.ValueKind != JsonValueKind.Object) return;
            foreach (var prop in files.EnumerateObject())
            {
                try
                {
                    var v = prop.Value;
                    _index[prop.Name] = new IdxEntry
                    {
                        Dur = Num(v, "dur", 0),
                        Size = (long)Num(v, "size", 0),
                        MTime = Num(v, "mtime", 0),
                    };
                }
                catch { /* 单条坏数据跳过 */ }
            }
        }
        catch { /* 优化，失败静默 */ }
    }

    private void SaveIndex()
    {
        if (string.IsNullOrEmpty(_outRoot)) return;
        try
        {
            Directory.CreateDirectory(_outRoot);
            var files = new Dictionary<string, object>();
            foreach (var kv in _index)
                files[kv.Key] = new
                {
                    dur = Math.Round(kv.Value.Dur, 2),
                    size = kv.Value.Size,
                    mtime = kv.Value.MTime,
                };
            var json = Config.Serialize(new { version = 1, updated = Now(), files });
            File.WriteAllText(IndexPath, json, new UTF8Encoding(false));
        }
        catch { /* 优化，失败静默 */ }
    }

    private static double Num(JsonElement v, string key, double def)
    {
        if (v.ValueKind == JsonValueKind.Object && v.TryGetProperty(key, out var e))
        {
            if (e.ValueKind == JsonValueKind.Number && e.TryGetDouble(out var d)) return d;
            if (e.ValueKind == JsonValueKind.String &&
                double.TryParse(e.GetString(), NumberStyles.Any,
                               CultureInfo.InvariantCulture, out var d2)) return d2;
        }
        return def;
    }
}
