using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xqd.Core;

namespace Xqd.Cli;

/// <summary>failed_list / failed 字典里的失败条目。</summary>
public sealed class FailedEntry
{
    public FailedEntry() { }
    public string camp { get; set; } = "";
    public string title { get; set; } = "";
    public string error { get; set; } = "";
}

/// <summary>
/// state/batch_state.json 的落盘结构 —— 记录已完成 / 失败，供重跑续跑。
/// completed 的主键是「营名|课序号」；重跑时跳过 completed 与磁盘上已完整的成品。
/// </summary>
public sealed class BatchStateData
{
    public BatchStateData() { }
    public int done { get; set; }
    public int fail { get; set; }
    public int skip { get; set; }
    public int total { get; set; }
    public string ts { get; set; } = "";
    public Dictionary<string, string> completed { get; set; } = new();
    public Dictionary<string, string> failed { get; set; } = new();
    public List<FailedEntry> failed_list { get; set; } = new();
}

/// <summary>
/// 全量批处理流水线 —— 对照 xqd_batch.py / xqd_pdl.py。
/// 网络 / 引擎逻辑全部走公共契约（Services.CreatePlatform / CreateDataSource /
/// Engine.DownloadAsync / History），本类只负责计划、并发编排、断点状态与中文日志。
/// </summary>
public sealed class BatchRunner
{
    private sealed class Job
    {
        public Camp Camp;
        public Lesson Lesson;
        public string OutPath;
        public string Key;
    }

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        PropertyNameCaseInsensitive = true,
    };
    private static readonly object PrintLock = new();

    private readonly CliOptions _opt;
    private readonly IPlatform _platform;           // 采集：--platform
    private readonly IDataSource _downloadSource;   // 下载链路：--mode
    private readonly SemaphoreSlim _dsGate = new(1, 1);
    private readonly object _lock = new();
    private readonly object _saveLock = new();
    private readonly string _stateFile;
    private readonly DateTime _t0 = DateTime.Now;

    private BatchStateData _data;
    private readonly List<FailedEntry> _failed = new();
    private int _ok, _fail, _skip, _total;

    public BatchRunner(CliOptions opt)
    {
        _opt = opt;
        // 采集平台与下载链路分别装配，api / adb 两类语义都保留。
        _platform = Services.CreatePlatform(opt.Platform, Creds.LoadCookie());
        var mode = opt.Mode == "adb" ? DataSourceMode.Adb : DataSourceMode.Api;
        _downloadSource = Services.CreateDataSource(mode, Creds.LoadCookie());
        _stateFile = Path.Combine(AppContext.BaseDirectory, "state", "batch_state.json");
    }

    public async Task RunAsync()
    {
        _data = LoadState();
        Log("开始建计划…");
        var plan = await BuildPlanAsync().ConfigureAwait(false);
        _total = plan.Count;
        Log($"计划 {_total} 节，输出目录 {_opt.Out}，课程级并发 {_opt.Workers}，"
          + $"分片并发 {_opt.SegWorkers}，画质 {_opt.Quality}，数据源 {_opt.Mode}，平台 {_opt.Platform}");
        Directory.CreateDirectory(_opt.Out);

        // 课级并发 workers；每节课内部的分片并发 seg-workers 交给引擎。
        await Parallel.ForEachAsync(plan,
            new ParallelOptions { MaxDegreeOfParallelism = Math.Max(1, _opt.Workers) },
            async (job, ct) => await ProcessJobAsync(job, ct).ConfigureAwait(false))
            .ConfigureAwait(false);

        SaveState();
        double minutes = (DateTime.Now - _t0).TotalMinutes;
        Log($"全部结束：完成={_ok} 失败={_fail} 跳过={_skip} 用时 {minutes:0.0} 分钟");
        if (_failed.Count > 0)
        {
            Log($"失败清单（{_failed.Count}）：");
            foreach (var f in _failed.Take(40))
                Log($"  {f.camp} / {f.title} : {f.error}");
        }
        Console.WriteLine($">>> 汇总 ok={_ok} fail={_fail} skip={_skip}");
    }

    // ── 计划：按 tab 拉营 → 逐营拉课表 → 预先分配成品路径 ──
    private async Task<List<Job>> BuildPlanAsync()
    {
        var plan = new List<Job>();
        var tabs = (_opt.Tabs ?? "").Split(',',
            StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        foreach (var tab in tabs)
        {
            List<Camp> camps;
            try
            {
                await _dsGate.WaitAsync().ConfigureAwait(false);
                try { camps = await _platform.ListCampsAsync(tab).ConfigureAwait(false); }
                finally { _dsGate.Release(); }
            }
            catch (Exception e)
            {
                Log($"营列表拉取失败 [{tab}]：{e.Message}");
                continue;
            }

            foreach (var camp in camps)
            {
                if (string.IsNullOrEmpty(camp.Name)) continue;
                // --only：命中营名则整营，否则只跑命中课名的课。
                bool campHit = string.IsNullOrEmpty(_opt.Only) ||
                               camp.Name.Contains(_opt.Only, StringComparison.Ordinal);
                List<Lesson> lessons;
                try
                {
                    await _dsGate.WaitAsync().ConfigureAwait(false);
                    try { lessons = await _platform.CampCatalogAsync(camp).ConfigureAwait(false); }
                    finally { _dsGate.Release(); }
                }
                catch (Exception e)
                {
                    Log($"课表拉取失败 {camp.Name}：{e.Message}");
                    continue;
                }

                // ★ 成品路径在建计划阶段一次性定好，避免并发时命名漂移。
                var folder = Path.Combine(_opt.Out, Naming.CampFolder(camp.Name));
                foreach (var l in lessons)
                {
                    if (!campHit && !(l.Title ?? "").Contains(_opt.Only, StringComparison.Ordinal))
                        continue;
                    plan.Add(new Job
                    {
                        Camp = camp,
                        Lesson = l,
                        OutPath = Path.Combine(folder, Naming.CourseFilename(l)),
                        Key = camp.Name + "|" + l.Index,
                    });
                }
            }
        }
        return plan;
    }

    // ── 单节：失败记录并继续，不中断整体 ──
    private async Task ProcessJobAsync(Job job, CancellationToken ct)
    {
        try { await ProcessOneAsync(job, ct).ConfigureAwait(false); }
        catch (Exception e) { MarkFail(job, "异常：" + e.Message); }
    }

    private async Task ProcessOneAsync(Job job, CancellationToken ct)
    {
        bool done;
        lock (_lock) done = _data.completed.ContainsKey(job.Key);
        if (done || AlreadyDone(job.OutPath))
        {
            MarkSkip(job);
            return;
        }

        // 现场解析播放地址（按 --mode 装配的数据源），签名天然新鲜。
        string playUrl = "";
        try
        {
            await _dsGate.WaitAsync(ct).ConfigureAwait(false);
            try { playUrl = await _downloadSource.ResolveAsync(job.Camp, job.Lesson, ct).ConfigureAwait(false); }
            finally { _dsGate.Release(); }
        }
        catch (Exception e)
        {
            Log($"解析失败 {job.Camp.Name} / {job.Lesson.Title}：{e.Message}");
        }
        if (string.IsNullOrEmpty(playUrl))
        {
            MarkFail(job, "播放地址解析失败");
            return;
        }

        var dir = Path.GetDirectoryName(job.OutPath);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        Log($"下载 {job.Camp.Name} / {job.Lesson.Title}");

        var req = new DownloadRequest
        {
            Camp = job.Camp,
            Lesson = job.Lesson,
            OutPath = job.OutPath,
            Quality = _opt.Quality,
            SegmentWorkers = _opt.SegWorkers,   // 每节课分片并发
            DataSource = _downloadSource,
            PlayUrl = playUrl,
            SegDir = Services.History.PartsDirFor(job.OutPath),
            KeepParts = false,
        };

        DownloadResult result;
        try
        {
            result = await Services.Engine.DownloadAsync(req, null, null, ct)
                                    .ConfigureAwait(false);
        }
        catch (Exception e)
        {
            MarkFail(job, e.Message);
            return;
        }

        if (result != null && result.Ok) MarkOk(job);
        else MarkFail(job, result?.Message ?? "下载失败");
    }

    private static bool AlreadyDone(string path)
    {
        try { return File.Exists(path) && new FileInfo(path).Length > 100000; }
        catch { return false; }
    }

    // ── 计数 / 断点状态 ──
    private void MarkOk(Job job)
    {
        lock (_lock)
        {
            _ok++;
            _data.completed[job.Key] = job.OutPath;
            _data.failed.Remove(job.Key);
        }
        Log($"完成 {job.Camp.Name} / {job.Lesson.Title}");
        PrintProgress();
        SaveState();
    }

    private void MarkSkip(Job job)
    {
        lock (_lock) { _skip++; _data.completed[job.Key] = job.OutPath; }
        Log($"跳过（已存在）{job.Camp.Name} / {job.Lesson.Title}");
        PrintProgress();
        SaveState();
    }

    private void MarkFail(Job job, string error)
    {
        var entry = new FailedEntry
        { camp = job.Camp.Name, title = job.Lesson.Title, error = error ?? "" };
        lock (_lock)
        {
            _fail++;
            _failed.Add(entry);
            _data.failed[job.Key] = entry.error;
        }
        Log($"失败 {job.Camp.Name} / {job.Lesson.Title}：{entry.error}");
        PrintProgress();
        SaveState();
    }

    private void PrintProgress()
    {
        int ok, fail, skip, total;
        lock (_lock) { ok = _ok; fail = _fail; skip = _skip; total = _total; }
        double minutes = (DateTime.Now - _t0).TotalMinutes;
        lock (PrintLock)
            Console.WriteLine($">>> 进度 {ok + fail + skip}/{total}  完成={ok} 失败={fail} "
                            + $"跳过={skip}  已用 {minutes:0.0} 分钟");
    }

    private BatchStateData LoadState()
    {
        try
        {
            if (!File.Exists(_stateFile)) return new BatchStateData();
            var d = JsonSerializer.Deserialize<BatchStateData>(
                File.ReadAllText(_stateFile, Encoding.UTF8), JsonOpts);
            if (d == null) return new BatchStateData();
            d.completed ??= new Dictionary<string, string>();
            d.failed ??= new Dictionary<string, string>();
            d.failed_list ??= new List<FailedEntry>();
            return d;
        }
        catch (Exception e)
        {
            Log("读取断点状态失败（按全新任务处理）：" + e.Message);
            return new BatchStateData();
        }
    }

    private void SaveState()
    {
        BatchStateData snap;
        lock (_lock)
        {
            snap = new BatchStateData
            {
                done = _ok,
                fail = _fail,
                skip = _skip,
                total = _total,
                ts = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                completed = new Dictionary<string, string>(_data.completed),
                failed = new Dictionary<string, string>(_data.failed),
                failed_list = new List<FailedEntry>(_failed),
            };
        }
        lock (_saveLock)
        {
            try
            {
                var dir = Path.GetDirectoryName(_stateFile);
                if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                var tmp = _stateFile + ".tmp";
                File.WriteAllText(tmp, JsonSerializer.Serialize(snap, JsonOpts),
                                  new UTF8Encoding(false));
                File.Move(tmp, _stateFile, true);   // 原子替换，避免写一半留下截断状态
            }
            catch (Exception e)
            {
                Log("保存断点状态失败：" + e.Message);
            }
        }
    }

    private static void Log(string msg)
    {
        lock (PrintLock) Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] {msg}");
    }
}
