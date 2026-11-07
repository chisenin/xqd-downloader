using System;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core.Engine;

/// <summary>
/// 直链媒体（AUDIO 类）下载 —— 对应 xqd_engine.download_direct。
///
/// ★ 保持原始格式，不塞进 MP4（无必要且二次转码失真）。
/// ★ 必须用 ffprobe 探真实容器给扩展名：Content-Type 一律 audio/mpeg 不可信
///   （URL 后缀 .mp3 实际可能是 M4A/AAC 或带 mjpeg 封面的真 MP3）。
/// ★ 临时文件用随机名（mkstemp），不能用固定名 —— 并发下载同营不同课会互相覆盖，产出截断成品。
/// ★ 流式读取（64KB 一块），每块前检查暂停，进度用字节占比（Unit="byte"）。
/// </summary>
internal static class DirectDownloader
{
    public static async Task<(bool ok, string msg, string final)> DownloadAsync(
        string url, string outPath, double expectDuration,
        DownloadCallbacks cb, DownloadControl control, CancellationToken ct)
    {
        // 随机临时文件名，避免并发下载同营不同课时互相覆盖（不能用固定名，否则会互相截断）。
        // 放成品同目录而非系统 temp：与 os.replace 一样走同卷原子移动，避免跨盘 Move 失败。
        string outDir = Path.GetDirectoryName(outPath);
        if (string.IsNullOrEmpty(outDir)) outDir = ".";
        Directory.CreateDirectory(outDir);
        string raw = Path.Combine(outDir,
                                  ".xqd_direct_" + Guid.NewGuid().ToString("N") + ".bin");
        try
        {
            var (got, _) = await StreamToRawAsync(url, raw, cb, control, ct)
                                     .ConfigureAwait(false);
            if (got <= 0) return (false, "直链下载失败（内容为空）", outPath);

            string ext = MediaProbe.AudioExtFor(raw);
            string final = MediaProbe.SwapExt(outPath, ext);
            string dir = Path.GetDirectoryName(final);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            // os.replace 语义：移动并覆盖（此时流已全部关闭，文件不再被占用）
            File.Move(raw, final, true);

            if (expectDuration > 0.0)
            {
                double actual = MediaProbe.ProbeDuration(final);
                if (actual <= 0.0) return (false, "成品无法解析（可能损坏）", final);
                if (Math.Abs(actual - expectDuration) > Math.Max(3.0, expectDuration * 0.01))
                    return (false, "时长不符："
                        + actual.ToString("0.0", CultureInfo.InvariantCulture)
                        + "s vs 期望 "
                        + expectDuration.ToString("0.0", CultureInfo.InvariantCulture) + "s", final);
            }

            string msg = (new FileInfo(final).Length / 1048576.0)
                .ToString("0.0", CultureInfo.InvariantCulture) + " MB（原格式 " + ext + "）";
            return (true, msg, final);
        }
        finally
        {
            try { if (File.Exists(raw)) File.Delete(raw); } catch { }
        }
    }

    /// <summary>
    /// 流式 GET → 写临时文件，返回 (已收字节, Content-Length)。
    /// 用 Net.CreateClient（禁用系统代理），一次请求同时拿到长度和流。
    /// </summary>
    private static async Task<(long got, long total)> StreamToRawAsync(
        string url, string raw, DownloadCallbacks cb,
        DownloadControl control, CancellationToken ct)
    {
        using var client = Net.CreateClient(1800);
        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct);
        linked.CancelAfter(TimeSpan.FromSeconds(1800));

        using var resp = await client.SendAsync(
            req, HttpCompletionOption.ResponseHeadersRead, linked.Token).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();

        long total = resp.Content.Headers.ContentLength ?? 0L;
        using var stream = await resp.Content.ReadAsStreamAsync(linked.Token).ConfigureAwait(false);
        using var fs = new FileStream(raw, FileMode.Create, FileAccess.Write,
                                      FileShare.Read, 65536);
        var buf = new byte[65536];
        long got = 0L;

        while (true)
        {
            // ★ 暂停点：每取一块之前检查；ct 取消由 WaitIfPausedAsync / ReadAsync 抛 OCE
            await SegmentDownloader.WaitPauseAsync(control, ct).ConfigureAwait(false);
            int n = await stream.ReadAsync(buf, 0, buf.Length, linked.Token).ConfigureAwait(false);
            if (n <= 0) break;
            await fs.WriteAsync(buf, 0, n, linked.Token).ConfigureAwait(false);
            got += n;
            try
            {
                cb?.OnProgress(new ProgressInfo
                {
                    DoneBytes = got,
                    TotalBytes = total > 0 ? total : got,
                    DoneDuration = 0.0,
                    TotalDuration = 0.0,
                    Unit = "byte",     // 直链音频无分片时长，用字节占比
                });
            }
            catch { /* 回调不可信 */ }
        }
        return (got, total);
    }
}
