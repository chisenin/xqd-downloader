using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core.Engine;

/// <summary>
/// 并行分片下载 —— 对应 xqd_engine.download_segments / _dl_all / _sample_segments / _seg_name。
///
/// ★ 总字节数必须均匀 12 片等距抽样外推：step=(n-1)/(12-1)，去重排序，片数≤12 全取。
///   取前 3 片实测高估 37.3%（直播课开头码率高）；抽样失败的分片不计入平均。
///   抽样片写进 seg_dir 复用，不额外浪费请求。
/// ★ 进度用「时长占比」（每片时长精确，总字节是估算）；ProgressInfo 同时给出
///   DoneBytes 与 DoneDuration —— GUI 有两个独立速率计（字节→速度列，内容时长→ETA）。
/// ★ 分片本地命名 %05d_&lt;basename&gt;：%05d 前缀保证字典序==数值序（否则 v.ts_10 排在 v.ts_2 前）；
///   basename 跨会话 150/150 稳定，只有 ?sign= 变 → 按名落盘即可跨进程复用。
/// </summary>
internal static class SegmentDownloader
{
    private const int SampleCount = 12;

    /// <summary>对应 _seg_name(url, i)。</summary>
    public static string SegName(string url, int i)
    {
        var (path, _) = Util.SplitQuery(url);
        int slash = path.LastIndexOf('/');
        string name = slash >= 0 ? path.Substring(slash + 1) : path;
        if (string.IsNullOrEmpty(name))
            name = "seg" + i.ToString("D5", CultureInfo.InvariantCulture);
        return i.ToString("D5", CultureInfo.InvariantCulture) + "_" + name;
    }

    /// <summary>统一暂停/取消检查点：暂停时等待，ct 取消抛 OperationCanceledException。</summary>
    public static async Task WaitPauseAsync(DownloadControl control, CancellationToken ct)
    {
        if (control != null)
            await control.WaitIfPausedAsync(ct).ConfigureAwait(false);
        else
            ct.ThrowIfCancellationRequested();
    }

    /// <summary>
    /// 均匀抽 12 片（或全取），下载并写进 seg_dir，返回「外推总字节数」。
    /// 对应 _sample_segments + _dl_all 里的 avg*n。
    /// </summary>
    public static async Task<long> SampleAsync(List<Segment> segments, string segDir,
                                               DownloadControl control, CancellationToken ct)
    {
        int n = segments.Count;
        if (n == 0) return 0L;

        var idxs = new List<int>();
        if (n <= SampleCount)
        {
            for (int i = 0; i < n; i++) idxs.Add(i);
        }
        else
        {
            double step = (n - 1) / (double)(SampleCount - 1);
            var set = new SortedSet<int>();
            for (int i = 0; i < SampleCount; i++)
                set.Add((int)Math.Round(i * step, MidpointRounding.ToEven));
            idxs.AddRange(set);
        }

        var sizes = new List<long>();
        foreach (int i in idxs)
        {
            await WaitPauseAsync(control, ct).ConfigureAwait(false);
            string url = segments[i].Url;
            string local = Path.Combine(segDir, SegName(url, i));

            byte[] body = null;
            // ★ 续传时优先读本地已有分片，不发请求（用户流量昂贵）
            if (File.Exists(local))
            {
                try { body = File.ReadAllBytes(local); }
                catch { body = null; }
            }
            if (body == null || body.Length == 0)
            {
                try { body = await Net.GetBytesAsync(url, 30, null, ct).ConfigureAwait(false); }
                catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
                catch { body = null; }
                if (body != null && body.Length > 0)
                {
                    // 抽样片写进 seg_dir，download_segments 会直接跳过
                    try { File.WriteAllBytes(local, body); } catch { }
                }
            }
            // 抽样失败的分片不计入平均
            if (body != null && body.Length > 0) sizes.Add(body.Length);
        }

        if (sizes.Count == 0) return 0L;
        double avg = sizes.Average();
        return (long)(avg * n);   // 与 Python int(avg * n) 一致：截断
    }

    /// <summary>
    /// 并行下载所有分片，返回 (成功数, 失败数, 字节数)。对应 download_segments。
    /// workers 默认 States.SegmentWorkers = 12。
    /// </summary>
    public static async Task<(int done, int fail, long bytes)> DownloadSegmentsAsync(
        List<Segment> segments, string segDir, int workers, long totalBytes,
        DownloadCallbacks cb, DownloadControl control, CancellationToken ct)
    {
        int n = segments.Count;
        if (n == 0) return (0, 0, 0L);
        Directory.CreateDirectory(segDir);

        double totalDur = 0.0;
        foreach (var s in segments) totalDur += s.Duration;

        var gate = new object();
        long doneBytes = 0L;
        double doneDur = 0.0;
        int done = 0;
        int next = -1;

        void Report()
        {
            ProgressInfo snap;
            lock (gate)
            {
                snap = new ProgressInfo
                {
                    DoneBytes = doneBytes,
                    TotalBytes = totalBytes,
                    DoneDuration = doneDur,
                    TotalDuration = totalDur,
                    Unit = "dur",     // 分片视频：进度用内容时长占比
                };
            }
            try { cb?.OnProgress(snap); } catch { /* 回调不可信 */ }
        }

        async Task Worker()
        {
            while (true)
            {
                // ★ 暂停点：在领新分片之前等，暂停后不再发新请求
                await WaitPauseAsync(control, ct).ConfigureAwait(false);
                int i = Interlocked.Increment(ref next);
                if (i >= n) return;

                string url = segments[i].Url;
                double dur = segments[i].Duration;
                string path = Path.Combine(segDir, SegName(url, i));

                // ★ 断点续下：已下好的分片不重复下载（跨会话续传的关键）
                if (File.Exists(path))
                {
                    long sz = 0L;
                    try { sz = new FileInfo(path).Length; } catch { }
                    if (sz > 0)
                    {
                        lock (gate) { done++; doneBytes += sz; doneDur += dur; }
                        Report();
                        continue;
                    }
                }

                for (int attempt = 0; attempt < 3; attempt++)
                {
                    // 每次重试前也检查暂停
                    await WaitPauseAsync(control, ct).ConfigureAwait(false);
                    byte[] body = null;
                    try { body = await Net.GetBytesAsync(url, 40, null, ct).ConfigureAwait(false); }
                    catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
                    catch { body = null; }

                    if (body != null && body.Length > 0)
                    {
                        try
                        {
                            File.WriteAllBytes(path, body);
                            lock (gate) { done++; doneBytes += body.Length; doneDur += dur; }
                            break;
                        }
                        catch (IOException) { /* 落盘失败，重试 */ }
                        catch (UnauthorizedAccessException) { }
                    }
                    if (attempt < 2)
                        await Task.Delay(1000 * (attempt + 1), ct).ConfigureAwait(false);
                }
                Report();
            }
        }

        int w = Math.Max(1, workers);
        var tasks = new Task[w];
        for (int k = 0; k < w; k++) tasks[k] = Task.Run((Func<Task>)Worker);
        await Task.WhenAll(tasks).ConfigureAwait(false);

        return (done, n - done, doneBytes);
    }
}
