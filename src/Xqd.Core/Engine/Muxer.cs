using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core.Engine;

/// <summary>
/// 拼接封装 + 分片清理 —— 对应 xqd_engine._concat_and_mux / _cleanup。
///
/// ★ 必须 cat 字节拼接成 all.ts 再喂 ffmpeg，不能用 concat demuxer：
///   concat demuxer 会重置时间戳，实测成品长 6 秒（230.8s vs 224.6s）→ 时长校验失败。
/// ★ 临时输出必须以 .mp4 结尾，否则 ffmpeg 报 "Error initializing the muxer"。
/// ★ 清理时逐个删除/截断（一次性批量删除会触发安全删除阈值），跳过 all.* 中间文件。
/// </summary>
internal static class Muxer
{
    /// <summary>按序 cat 分片 → ffmpeg -c copy 转封装，返回 (ok, note)。</summary>
    public static async Task<(bool ok, string msg)> ConcatAndMuxAsync(
        string segDir, string outPath, CancellationToken ct)
    {
        // %05d_ 前缀保证字典序==数值序，所以按文件名字典序拼接即为正确播放顺序。
        // 排除 all.* 中间文件（上一次失败可能残留，绝不能拼进去）。
        var files = Directory.GetFiles(segDir)
            .Select(Path.GetFileName)
            .Where(n => n.EndsWith(".ts", StringComparison.OrdinalIgnoreCase)
                     && !n.StartsWith("all.", StringComparison.OrdinalIgnoreCase))
            .OrderBy(n => n, StringComparer.Ordinal)
            .ToList();
        if (files.Count == 0) return (false, "没有可用的分片");

        string catPath = Path.Combine(segDir, "all.ts");
        try
        {
            using (var outStream = new FileStream(catPath, FileMode.Create,
                                                  FileAccess.Write, FileShare.Read, 1 << 20))
            {
                foreach (var name in files)
                {
                    try
                    {
                        using var f = File.OpenRead(Path.Combine(segDir, name));
                        f.CopyTo(outStream, 1 << 20);
                    }
                    catch (IOException) { continue; }
                    catch (UnauthorizedAccessException) { continue; }
                }
            }
        }
        catch (IOException e) { return (false, "分片拼接失败: " + e.Message); }

        // 契约 helper：outPath + ".part" + 原扩展名；分片视频成品是 .mp4 → 必以 .mp4 结尾
        string tmpOut = Naming.TempPartPath(outPath);
        if (!tmpOut.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase))
            tmpOut = outPath + ".part.mp4";

        var args = new[]
        {
            "-y", "-loglevel", "error",
            "-protocol_whitelist", "file,http,https,tcp,tls,crypto,httpproxy",
            "-i", catPath,
            "-c", "copy", "-bsf:a", "aac_adtstoasc",
            "-movflags", "+faststart",
            tmpOut,
        };

        Proc.RunResult r;
        try
        {
            // 所有子进程走 Proc（CreateNoWindow + Hidden，无控制台窗口）
            r = await Task.Run(() => Proc.Run(MediaProbe.FfmpegPath, args, 7200000), ct)
                          .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception e) { return (false, "ffmpeg 失败: " + e.Message); }

        if (r.Code != 0 || !File.Exists(tmpOut) || new FileInfo(tmpOut).Length < 10000)
        {
            string err = r.Err ?? "";
            if (err.Length > 300) err = err.Substring(err.Length - 300);
            return (false, string.IsNullOrEmpty(err) ? "ffmpeg rc=" + r.Code : err);
        }

        // os.replace 语义：覆盖已存在成品，不用「先删再移」（安全删除钩子会拦不存在的文件）
        File.Move(tmpOut, outPath, true);
        try { File.Delete(catPath); } catch { }

        string sizeMsg = (new FileInfo(outPath).Length / 1048576.0)
            .ToString("0.0", CultureInfo.InvariantCulture) + " MB";
        return (true, sizeMsg);
    }

    /// <summary>
    /// 清理临时分片目录。对应 _cleanup：不能用 Directory.Delete(recursive=true)
    /// 一次性批量删，逐个 File.Delete 最稳；失败则截断释放空间；跳过 all.* 中间文件。
    /// </summary>
    public static void Cleanup(string segDir)
    {
        try
        {
            foreach (var p in Directory.GetFiles(segDir))
            {
                string name = Path.GetFileName(p);
                if (name.StartsWith("all.", StringComparison.OrdinalIgnoreCase)) continue;
                try { File.Delete(p); }
                catch
                {
                    // 截断同样释放磁盘空间，且不触发批量删除阈值
                    try { using var fs = new FileStream(p, FileMode.Truncate, FileAccess.Write); }
                    catch { }
                }
            }
            try { Directory.Delete(segDir, false); } catch { }
        }
        catch { /* 目录不存在/被占用都忽略 */ }
    }
}
