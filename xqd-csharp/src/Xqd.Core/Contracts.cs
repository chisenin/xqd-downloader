using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core;

// ════════════════════════════════════════════════════════════════════
//  跨模块契约 —— 所有前端（WPF GUI / 本地服务 / CLI）只依赖这些接口，
//  各模块并行实现时签名以此文件为准，不得另起一套。
// ════════════════════════════════════════════════════════════════════

/// <summary>历史记录（对应 xqd_history.make_record）。主键是成品路径。</summary>
public sealed class HistoryRecord
{
    public string path { get; set; } = "";
    public string title { get; set; } = "";
    public string camp { get; set; } = "";
    public string state { get; set; } = "";
    public long size { get; set; }
    public long down { get; set; }
    public long total { get; set; }
    public double done_dur { get; set; }
    public double total_dur { get; set; }
    public long duration { get; set; }
    public double ts { get; set; }

    public static HistoryRecord Make(string path, string title, string camp = "",
        string state = "", long size = 0, long down = 0, long total = 0,
        double doneDur = 0, double totalDur = 0, long duration = 0) => new()
    {
        path = path, title = title, camp = camp, state = state,
        size = size, down = down, total = total,
        done_dur = Math.Round(doneDur, 2), total_dur = Math.Round(totalDur, 2),
        duration = duration,
        ts = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
    };
}

public interface IHistoryStore
{
    List<HistoryRecord> Load(string path = null);
    bool Save(IEnumerable<HistoryRecord> items, string path = null);
    /// <summary>按 path 合并；已完成/失败不被「排队中/下载中/解析中」覆盖；进度只前进。</summary>
    bool Merge(List<HistoryRecord> history, HistoryRecord rec);
    List<HistoryRecord> Sort(List<HistoryRecord> history);
    string PartsKey(string outPath);
    string PartsDirFor(string outPath, string root = null);
    (long Bytes, int Count, long CacheBytes) PartsProgress(string segDir);
    long PurgeParts(string outPath, string root = null);
    long PurgeAllParts(string root = null);
    void PurgeOrphanParts(List<HistoryRecord> history, string root = null);
}

public sealed class ExistingState
{
    /// <summary>missing | ok | broken | legacy_ok</summary>
    public string Status { get; set; } = "missing";
    public string Path { get; set; } = "";
    public long Size { get; set; }
    public double Duration { get; set; }
    public bool IsOk => Status == "ok" || Status == "legacy_ok";
}

public interface IExistingChecker
{
    /// <summary>按文件名主键 + 10KB 门槛 + ffprobe 时长（容差 max(3s,1%)）判定。</summary>
    ExistingState Check(string campFolder, string stem, double expectDuration);
    void Invalidate(string campFolder);
}

public sealed class AuthResult
{
    public bool Ok { get; set; }
    public string Cookie { get; set; } = "";
    public string Message { get; set; } = "";
    /// <summary>true = 直接用了本机保存的授权，没有启动模拟器。</summary>
    public bool FromCache { get; set; }
}

public interface IAuthService
{
    /// <summary>
    /// 平时直接用保存的授权（不启动 MuMu）；仅首次 / forceMumu=true 才走模拟器。
    /// autoLaunch / autoClose 控制走模拟器时的自动启停。
    /// </summary>
    Task<AuthResult> EnsureAuthAsync(bool forceMumu = false, Action<string> onStatus = null,
                                     bool autoLaunch = true, bool autoClose = true,
                                     CancellationToken ct = default);
    Task<AuthResult> RefreshAsync(Action<string> onStatus = null,
                                  CancellationToken ct = default);
    void CloseAll();
}

public sealed class DownloadCallbacks
{
    /// <summary>阶段名：解析 / 下载 / 封装 / 校验。</summary>
    public Action<string> Phase { get; set; }
    public Action<ProgressInfo> Progress { get; set; }
    public Action<string> Log { get; set; }

    public void OnPhase(string p) => Phase?.Invoke(p);
    public void OnProgress(ProgressInfo p) => Progress?.Invoke(p);
    public void OnLog(string m) => Log?.Invoke(m);
}

/// <summary>暂停 / 取消控制。暂停时冻结倒计时，分片必须保留。</summary>
public sealed class DownloadControl
{
    private volatile bool _paused;
    private volatile bool _cancelled;

    public bool Paused { get => _paused; set => _paused = value; }
    public bool Cancelled { get => _cancelled; set => _cancelled = value; }
    public bool StopRequested => _cancelled;

    public async Task WaitIfPausedAsync(CancellationToken ct = default)
    {
        while (_paused && !_cancelled && !ct.IsCancellationRequested)
            await Task.Delay(120, ct).ConfigureAwait(false);
        ct.ThrowIfCancellationRequested();
        if (_cancelled) throw new OperationCanceledException("已取消");
    }
}

/// <summary>数据源：api（默认，不需要模拟器）/ adb（旧路径）。</summary>
public interface IDataSource
{
    DataSourceMode Mode { get; }
    Task<List<Camp>> ListCampsAsync(string kind, CancellationToken ct = default);
    Task<List<Lesson>> CampCatalogAsync(Camp camp, CancellationToken ct = default);
    Task<string> ResolveAsync(Camp camp, Lesson lesson, CancellationToken ct = default);
    Task<(bool Ok, string Message)> CheckAuthAsync(CancellationToken ct = default);
}

public interface IPlatform : IDataSource
{
    string PlatformId { get; }
    string DisplayName { get; }
    IReadOnlyList<string> CampKinds { get; }
}

public interface IDownloadEngine
{
    Task<DownloadResult> DownloadAsync(DownloadRequest req,
                                       DownloadCallbacks cb = null,
                                       DownloadControl control = null,
                                       CancellationToken ct = default);
}

/// <summary>默认装配点：前端统一从这里取实现，避免各处自己 new。</summary>
public static class Services
{
    public static IPlatform CreatePlatform(string platformId = "qianliao", string cookie = "") =>
        new Xqd.Core.Api.QianliaoPlatform(cookie);

    public static IDataSource CreateDataSource(DataSourceMode mode, string cookie = "") =>
        mode == DataSourceMode.Adb
            ? (IDataSource)new Xqd.Core.Adb.AdbDataSource()
            : new Xqd.Core.Api.QianliaoPlatform(cookie);

    public static readonly IDownloadEngine Engine = new Xqd.Core.Engine.DownloadEngine();
    public static readonly IHistoryStore History = new Xqd.Core.History.HistoryStore();
    public static readonly IAuthService Auth = new Xqd.Core.Auth.MumuAuth();

    public static IExistingChecker CreateChecker(string outRoot) =>
        new Xqd.Core.Dedupe.ExistingChecker(outRoot);
}
