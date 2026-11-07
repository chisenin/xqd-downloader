using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Xqd.Core;

namespace Xqd.Server;

/// <summary>POST /api/download 的 items 元素（ui.html 只提交 title / when）。</summary>
public sealed class DownloadItem
{
    public string Title = "";
    public string When = "";
}

/// <summary>
/// 业务动作 —— 对照 xqd_server.py 的 do_list_camps / do_catalog / run_sweep /
/// run_download / run_download_api / do_files。
///
/// 数据源一律通过按 --mode 创建的实例（Services.CreateDataSource）取得，
/// 所有访问经 _gate 串行化：既等价 Python 的 adb_guard（ADB 操作不能并发），
/// 也保护 Core 平台适配器内部的缓存字典（非线程安全）。
/// </summary>
public sealed class ServerActions
{
    private readonly ServerState _state;
    private readonly string _mode;
    private readonly IDataSource _dataSource;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly object _campLock = new();
    private readonly Dictionary<string, Camp> _campByName = new();
    private readonly string _quality;
    private readonly int _segWorkers;

    public ServerActions(ServerState state, string mode, AppConfig cfg)
    {
        _state = state;
        _mode = mode;
        // 契约指定的两种装配方式，原样保留两类语义。
        _dataSource = mode == "adb"
            ? Services.CreateDataSource(DataSourceMode.Adb)
            : Services.CreateDataSource(DataSourceMode.Api, Creds.LoadCookie());

        var q = cfg?.quality ?? "max";
        _quality = (q == "720" || q == "1080") ? q : "max";
        _segWorkers = cfg != null && cfg.seg_workers > 0
            ? cfg.seg_workers : States.SegmentWorkers;
    }

    // ── 数据源串行门（等价 adb_guard）──
    private async Task<T> Gated<T>(Func<Task<T>> f)
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        _state.EnterBusy();
        try { return await f().ConfigureAwait(false); }
        finally { _state.LeaveBusy(); _gate.Release(); }
    }

    private Camp CampOf(string name)
    {
        lock (_campLock)
            return _campByName.TryGetValue(name ?? "", out var c)
                ? c : new Camp { Name = name ?? "" };
    }

    private void Remember(IEnumerable<Camp> camps)
    {
        lock (_campLock)
            foreach (var c in camps)
                if (!string.IsNullOrEmpty(c?.Name)) _campByName[c.Name] = c;
    }

    /// <summary>skuType → 中文营类型（与 xqd_api.list_camps 判定一致）。</summary>
    private static string CampType(Camp c)
    {
        var sku = c?.SkuType ?? "";
        if (sku == "FINANCIAL") return "正式营";
        if (sku == "LAUNCH" || sku == "INTENTION") return "体验营";
        var kind = c?.Kind ?? "";
        if (!string.IsNullOrEmpty(kind) && kind != "全部") return kind;
        return "公开课";
    }

    // ── GET /api/camps ──
    public async Task<Dictionary<string, object>> ListCampsAsync(string tab)
    {
        var camps = await Gated(() => _dataSource.ListCampsAsync(tab ?? "全部"))
                          .ConfigureAwait(false);
        Remember(camps);

        var seen = new HashSet<string>(StringComparer.Ordinal);
        var list = new List<Dictionary<string, object>>();
        foreach (var c in camps)
        {
            // 「全部」按 CampId 去重（对齐 xqd_api.list_camps 的 seen 语义）。
            if (!string.IsNullOrEmpty(c.CampId) && !seen.Add(c.CampId)) continue;
            var type = CampType(c);
            list.Add(new Dictionary<string, object>
            {
                ["name"] = c.Name,
                ["badge"] = c.Count > 0 ? type + "•共" + c.Count + "课" : type,
                ["type"] = type,
                ["count"] = c.Count,
            });
        }
        return new Dictionary<string, object> { ["camps"] = list, ["mode"] = _mode };
    }

    // ── GET /api/courses ──
    public async Task<Dictionary<string, object>> CatalogAsync(string camp)
    {
        var lessons = await Gated(() => _dataSource.CampCatalogAsync(CampOf(camp)))
                          .ConfigureAwait(false);

        var items = new List<Dictionary<string, object>>();
        foreach (var l in lessons)
        {
            // api：课表一次取全、播放地址现场解析 → resolved 恒 true；
            // adb：只有拿到 fileId 才算已绑定（对齐 do_catalog 的 names 映射）。
            bool resolved = _mode == "api" ? true : !string.IsNullOrEmpty(l.FileId);
            items.Add(new Dictionary<string, object>
            {
                ["title"] = l.Title,
                ["when"] = l.When,
                ["index"] = l.Index,
                ["resolved"] = resolved,
                ["duration"] = l.Duration,
                ["type"] = l.Type,
            });
        }
        return new Dictionary<string, object>
        {
            ["camp"] = camp, ["items"] = items, ["mode"] = _mode,
        };
    }

    // ── GET /api/files ──
    public Dictionary<string, object> Files(string camp)
    {
        var root = _state.CurrentOutRoot();
        var list = new List<Dictionary<string, object>>();
        if (!string.IsNullOrEmpty(camp))
        {
            var folder = Path.Combine(root, Naming.CampFolder(camp));
            if (Directory.Exists(folder))
                foreach (var p in Directory.EnumerateFiles(folder))
                    AddFile(list, camp, p);
        }
        else if (Directory.Exists(root))
        {
            foreach (var d in Directory.EnumerateDirectories(root)
                                      .OrderBy(x => x, StringComparer.Ordinal))
                foreach (var p in Directory.EnumerateFiles(d))
                    AddFile(list, Path.GetFileName(d), p);
        }
        return new Dictionary<string, object> { ["files"] = list, ["out_root"] = root };
    }

    private static void AddFile(List<Dictionary<string, object>> list, string camp, string p)
    {
        var fn = Path.GetFileName(p);
        var ext = Path.GetExtension(fn).ToLowerInvariant();
        // Python 版只认 .mp4；这里一并覆盖音频课等常见成品容器。
        if (ext != ".mp4" && ext != ".mp3" && ext != ".m4a" &&
            ext != ".mkv" && ext != ".mov" && ext != ".aac") return;
        long size;
        try { size = new FileInfo(p).Length; } catch { return; }
        list.Add(new Dictionary<string, object>
        {
            ["camp"] = camp, ["name"] = fn, ["size"] = size, ["path"] = p,
        });
    }

    // ── POST /api/sweep（后台任务）──
    public async Task RunSweepAsync(string camp, TaskItem task)
    {
        try
        {
            if (_mode == "api")
            {
                // API 模式不需要 sweep：课表一次拿全、播放地址现场解析。
                _state.TaskLog(task, "API 模式无需绑定 fileId（课表已一次性取全）");
                _state.Update(task, t => t.Ok = 0);
                _state.FinishTask(task, "done");
                return;
            }

            var campObj = CampOf(camp);
            var lessons = await Gated(() => _dataSource.CampCatalogAsync(campObj))
                              .ConfigureAwait(false);

            int played = 0, total = lessons.Count;
            for (int i = 0; i < total; i++)
            {
                var l = lessons[i];
                int idx = i;
                _state.Update(task, t =>
                {
                    t.Current = l.Title;
                    if (total > 0) t.Progress = Math.Min(99.0, idx * 100.0 / total);
                });
                try
                {
                    // adb 路径逐节现场解析 = 逐节绑定文件地址（等价 A.sweep_camp）。
                    var url = await Gated(() => _dataSource.ResolveAsync(campObj, l))
                                  .ConfigureAwait(false);
                    if (!string.IsNullOrEmpty(url)) played++;
                }
                catch (Exception e)
                {
                    _state.TaskLog(task, "绑定失败 " + l.Title + "：" + e.Message);
                }
            }
            _state.Update(task, t => t.Ok = played);
            _state.TaskLog(task, $"绑定完成：{played}/{total} 节");
            _state.FinishTask(task, "done");
        }
        catch (Exception e)
        {
            _state.TaskLog(task, "异常终止：" + e.Message);
            _state.FinishTask(task, "error");
            _state.SetError(ServerState.Tail(e.ToString(), 600));
        }
    }

    // ── POST /api/download（后台任务）──
    public async Task RunDownloadAsync(string camp, List<DownloadItem> items, TaskItem task)
    {
        try
        {
            var r = await DownloadCoreAsync(camp, items, task).ConfigureAwait(false);
            _state.Update(task, t => { t.Ok = r.Ok; t.Fail = r.Fail; t.Skip = r.Skip; });
            _state.FinishTask(task, "done");
        }
        catch (Exception e)
        {
            // 包一层异常保护 —— 任何异常都要把任务标记为 error，不能静默挂起。
            _state.TaskLog(task, "异常终止：" + e.Message);
            _state.FinishTask(task, "error");
            _state.SetError(ServerState.Tail(e.ToString(), 600));
        }
    }

    /// <summary>对照 run_download / run_download_api：返回 (ok, fail, skip)。</summary>
    private async Task<(int Ok, int Fail, int Skip)> DownloadCoreAsync(
        string camp, List<DownloadItem> items, TaskItem task)
    {
        var root = _state.CurrentOutRoot();
        var folder = Path.Combine(root, Naming.CampFolder(camp));
        Directory.CreateDirectory(folder);

        var campObj = CampOf(camp);
        var catalog = await Gated(() => _dataSource.CampCatalogAsync(campObj))
                          .ConfigureAwait(false);

        // 按标题配对课表（同名取第一节，对齐 xqd_api.download_items 的 setdefault）。
        var byTitle = new Dictionary<string, Lesson>(StringComparer.Ordinal);
        foreach (var l in catalog)
            if (!string.IsNullOrEmpty(l.Title) && !byTitle.ContainsKey(l.Title))
                byTitle[l.Title] = l;

        int ok = 0, fail = 0, skip = 0;
        int total = items.Count;
        for (int i = 0; i < total; i++)
        {
            var it = items[i];
            var title = it.Title ?? "";
            int idx = i;
            double denom = total > 0 ? total : 1;
            _state.Update(task, t =>
            {
                t.Current = "准备：" + title;
                t.Progress = idx * 100.0 / denom;
            });

            byTitle.TryGetValue(title, out var lesson);
            // 规范命名：序号.课名.日期.扩展名；营目录用同一个 CampFolder。
            string filename = lesson != null
                ? Naming.CourseFilename(lesson)
                : Naming.CourseFilename(new Lesson
                {
                    Index = idx, Title = title, When = it.When,
                });
            var outPath = Path.Combine(folder, filename);

            if (File.Exists(outPath) && new FileInfo(outPath).Length > 100000)
            {
                _state.TaskLog(task, "已存在，跳过：" + title);
                skip++;
                _state.Update(task, t => t.Progress = (idx + 1) * 100.0 / denom);
                continue;
            }
            if (lesson == null)
            {
                _state.TaskLog(task, "课表里找不到：" + title);
                fail++;
                _state.Update(task, t => t.Progress = (idx + 1) * 100.0 / denom);
                continue;
            }

            // 现场解析：用本服务持有的（按 mode 创建的）数据源，签名天然新鲜。
            string playUrl = "";
            try
            {
                playUrl = await Gated(() => _dataSource.ResolveAsync(campObj, lesson))
                              .ConfigureAwait(false);
            }
            catch (Exception e)
            {
                _state.TaskLog(task, "解析失败 " + title + "：" + e.Message);
            }
            if (string.IsNullOrEmpty(playUrl))
            {
                _state.TaskLog(task, "拿不到播放地址：" + title);
                fail++;
                _state.Update(task, t => t.Progress = (idx + 1) * 100.0 / denom);
                continue;
            }

            var req = new DownloadRequest
            {
                Camp = campObj,
                Lesson = lesson,
                OutPath = outPath,
                Quality = _quality,
                SegmentWorkers = _segWorkers,
                DataSource = _dataSource,                       // 调用方持有的已授权实例
                PlayUrl = playUrl,                              // 已解析好的播放地址
                SegDir = Services.History.PartsDirFor(outPath), // 持久分片缓存
                KeepParts = false,
            };
            var cb = new DownloadCallbacks
            {
                Log = m => _state.TaskLog(task, m),
                Phase = ph => _state.Update(task, t => t.Current = title + " · " + ph),
                Progress = p => _state.Update(task, t =>
                {
                    t.Current = $"{title}（{p.Percent}%）";
                    t.Progress = (idx + p.Percent / 100.0) * 100.0 / denom;
                }),
            };

            _state.Update(task, t => t.Current = title);
            DownloadResult result;
            try
            {
                result = await Services.Engine.DownloadAsync(req, cb).ConfigureAwait(false);
            }
            catch (Exception e)
            {
                result = new DownloadResult { Ok = false, Message = e.Message };
            }

            if (result != null && result.Ok)
            {
                ok++;
                double mb = File.Exists(outPath)
                    ? new FileInfo(outPath).Length / 1048576.0 : 0;
                _state.TaskLog(task, $"✓ {title}  [{mb:0.0}MB] {result.Message}");
            }
            else
            {
                fail++;
                _state.TaskLog(task, "✗ " + title + "  " + (result?.Message ?? "下载失败"));
            }
            _state.Update(task, t => t.Progress = (idx + 1) * 100.0 / denom);
        }
        return (ok, fail, skip);
    }
}
