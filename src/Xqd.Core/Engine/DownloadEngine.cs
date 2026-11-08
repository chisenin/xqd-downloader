using System;
using System.Globalization;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core.Engine;

/// <summary>
/// 下载引擎（对外主入口）—— 完整移植 xqd_engine.download_lesson。
///
/// 阶段回调固定顺序：解析 → 下载 → 封装 → 校验；直链音频只有「解析」「下载」，没有封装阶段。
/// ★ 封装 / 校验阶段不发任何网络请求（GUI 靠这个释放网络槽位）。
/// ★ 暂停：control.WaitIfPausedAsync(ct)，暂停期间不删分片；ct 取消抛 OperationCanceledException。
/// ★ 清理条件：if (ownDir || (ok_result && !keepParts)) —— 引擎自建临时目录一律清；
///   调用方持久缓存成功才清、失败/中止必须保留（写反会删掉跨会话续传的本钱）。
/// </summary>
public sealed class DownloadEngine : IDownloadEngine
{
    /// <summary>无参构造：Services.Engine 直接 new 本类。</summary>
    public DownloadEngine() { }

    public async Task<DownloadResult> DownloadAsync(DownloadRequest req,
                                                     DownloadCallbacks cb = null,
                                                     DownloadControl control = null,
                                                     CancellationToken ct = default)
    {
        cb = cb ?? new DownloadCallbacks();
        control = control ?? new DownloadControl();
        try
        {
            // 优先用调用方指定的持久分片缓存（GUI 进度恢复与引擎必须看到同一份）；
            // 未提供时按 docs/11 D 节从成品路径派生。缓存归属由 ownDir 判定。
            string segDir = string.IsNullOrEmpty(req.SegDir)
                ? PersistentSegDir(req.OutPath) : req.SegDir;
            return await DownloadCoreAsync(req, cb, control, ct, segDir, req.KeepParts)
                         .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception e)
        {
            return new DownloadResult
            {
                Ok = false,
                Message = e.Message,
                OutPath = req.OutPath,
            };
        }
    }

    /// <summary>对应 download_lesson 的 resolve_url()：契约里唯一的播放地址解析入口。</summary>
    private static async Task<string> ResolveUrlAsync(DownloadRequest req,
                                                       DownloadCallbacks cb,
                                                       CancellationToken ct)
    {
        try
        {
            // ★ 调用方（GUI / Server / CLI）已经现场解析过播放地址时直接用，
            //   绝不重复 resolve —— 网络不稳定、流量昂贵，少一次请求是一次。
            //   签名每次都变，所以调用方传来的 URL 天然新鲜。
            if (!string.IsNullOrEmpty(req.PlayUrl)) return req.PlayUrl;

            // 其次复用调用方持有的已授权数据源（adb 模式尤其不能回退成 api）。
            IDataSource ds = req.DataSource;
            if (ds == null)
            {
                var cfg = Config.Load();
                var mode = string.Equals(cfg.mode, "adb", StringComparison.OrdinalIgnoreCase)
                    ? DataSourceMode.Adb : DataSourceMode.Api;
                ds = Services.CreateDataSource(mode, Creds.LoadCookie());
            }
            return await ds.ResolveAsync(req.Camp, req.Lesson, ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception e)
        {
            cb?.OnLog("解析播放地址失败：" + e.Message);
            return "";
        }
    }

    /// <summary>
    /// 持久分片缓存目录。优先用契约 IHistoryStore.PartsDirFor，保证与 GUI 进度恢复
    /// （PartsProgress）看到同一份缓存；回退到 docs/01 十七节 / docs/11 D 节规则：
    /// &lt;Config.PartsDir&gt;/&lt;md5(abspath(out_path))[:16]&gt;。
    /// </summary>
    private static string PersistentSegDir(string outPath)
    {
        try
        {
            string d = Services.History.PartsDirFor(outPath);
            if (!string.IsNullOrEmpty(d)) return d;
        }
        catch { /* History 尚未装配时回退全局规则 */ }

        try
        {
            string full = Path.GetFullPath(outPath);
            string key = Util.Md5Hex(full);
            if (key.Length > 16) key = key.Substring(0, 16);
            return Path.Combine(Config.PartsDir, key);
        }
        catch
        {
            return Path.Combine(Path.GetTempPath(), "xqd_" + Guid.NewGuid().ToString("N"));
        }
    }

    /// <summary>对应 xqd_engine.download_lesson 主体。</summary>
    private async Task<DownloadResult> DownloadCoreAsync(
        DownloadRequest req, DownloadCallbacks cb, DownloadControl control,
        CancellationToken ct, string segDir, bool keepParts)
    {
        string outPath = req.OutPath;
        double expectDuration = req.Lesson != null ? req.Lesson.Duration : 0.0;
        int workers = req.SegmentWorkers > 0 ? req.SegmentWorkers : States.SegmentWorkers;

        cb?.OnPhase("解析");
        string url = await ResolveUrlAsync(req, cb, ct).ConfigureAwait(false);
        if (string.IsNullOrEmpty(url)) return Fail("无法取得播放地址", outPath);

        var manifest = await ManifestParser.ParseAsync(url, req.Quality, ct).ConfigureAwait(false);
        if (manifest == null || manifest.Segments.Count == 0)
            return Fail(manifest != null ? manifest.Note : "清单解析失败", outPath);

        string outDir = Path.GetDirectoryName(outPath);
        if (!string.IsNullOrEmpty(outDir)) Directory.CreateDirectory(outDir);

        // 直链音频：只有「解析」「下载」，无封装阶段；且完全不涉及分片缓存目录
        if (manifest.Kind == ManifestKind.Direct)
        {
            cb?.OnPhase("下载");
            var direct = await DirectDownloader.DownloadAsync(
                url, outPath, expectDuration, cb, control, ct).ConfigureAwait(false);
            return Result(direct.ok, direct.msg, direct.final, expectDuration);
        }

        bool ownDir = segDir == null;
        if (ownDir)
            segDir = Path.Combine(Path.GetTempPath(), "xqd_" + Guid.NewGuid().ToString("N"));
        else
            Directory.CreateDirectory(segDir);

        bool okResult = false;
        try
        {
            cb?.OnPhase("下载");
            // 总字节 = 均匀 12 片等距抽样外推；抽样片已写进 seg_dir 会被直接复用
            long totalBytes = await SegmentDownloader.SampleAsync(
                manifest.Segments, segDir, control, ct).ConfigureAwait(false);
            var dl = await SegmentDownloader.DownloadSegmentsAsync(
                manifest.Segments, segDir, workers, totalBytes, cb, control, ct)
                .ConfigureAwait(false);
            if (!(dl.fail == 0 && dl.done > 0))
            {
                if (control != null && control.Cancelled) return Fail("已中止", outPath);
                return Fail("分片下载失败", outPath);
            }

            // 转封装前再确认一次没被暂停（暂停时不该开始转封装）
            await SegmentDownloader.WaitPauseAsync(control, ct).ConfigureAwait(false);

            // ★ 封装 / 校验阶段：cat 拼接 + ffmpeg + ffprobe，全是本地磁盘/CPU，不发网络请求
            cb?.OnPhase("封装");
            var mux = await Muxer.ConcatAndMuxAsync(segDir, outPath, ct).ConfigureAwait(false);
            if (!mux.ok) return Fail(mux.msg, outPath);

            cb?.OnPhase("校验");
            double duration = manifest.TotalDuration;
            if (expectDuration > 0.0)
            {
                double actual = MediaProbe.ProbeDuration(outPath);
                if (actual <= 0.0) return Fail("成品无法解析（可能损坏）", outPath);
                if (Math.Abs(actual - expectDuration) > Math.Max(3.0, expectDuration * 0.01))
                    return Fail("时长不符："
                        + actual.ToString("0.0", CultureInfo.InvariantCulture)
                        + "s vs 期望 "
                        + expectDuration.ToString("0.0", CultureInfo.InvariantCulture) + "s",
                        outPath);
                duration = actual;
            }

            okResult = true;
            return Result(true, manifest.Note + "，" + mux.msg, outPath, duration);
        }
        finally
        {
            // ★ 清理条件不可写反：失败/中止必须保留持久缓存，否则跨会话续传作废。
            //   ownDir=true  → 引擎自建临时目录，一律清。
            //   ownDir=false → 调用方持久缓存：成功才清（keepParts=true 连成功的也留）。
            if (ownDir || (okResult && !keepParts)) Muxer.Cleanup(segDir);
        }
    }

    private static DownloadResult Result(bool ok, string msg, string outPath, double duration)
    {
        long size = 0L;
        try { if (File.Exists(outPath)) size = new FileInfo(outPath).Length; } catch { }
        return new DownloadResult
        {
            Ok = ok,
            Message = msg,
            OutPath = outPath,
            Size = size,
            Duration = duration,
        };
    }

    private static DownloadResult Fail(string msg, string outPath) =>
        Result(false, msg, outPath, 0.0);
}
