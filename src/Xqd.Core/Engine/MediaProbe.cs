using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace Xqd.Core.Engine;

/// <summary>ffprobe -show_entries ... -of json 的解析结果（对应 xqd_engine.probe_media）。</summary>
internal sealed class MediaInfo
{
    public string FormatName { get; set; } = "";
    public double Duration { get; set; }
    public bool HasVideo { get; set; }
    public bool HasAudio { get; set; }
    public List<string> Codecs { get; set; } = new List<string>();
    public long Size { get; set; }
}

/// <summary>
/// ffmpeg/ffprobe 查找与探测 —— 对应 xqd_engine 的
/// _find_ffmpeg / probe_duration / probe_info / probe_media / audio_ext_for / swap_ext。
///
/// 所有子进程统一走 Xqd.Core.Proc（无控制台窗口、Qt 环境净化）。
/// 查找顺序：**工具自装目录**（~/.xqd_tool/ffmpeg/bin，v1.6.3 自动安装的在这）
///         → PATH → D:/user/chisenin/download/Programs/ffmpeg-8.0.1-essentials_build/bin
///         → C:/LEL/LEL-Downloader/Source/ffmpeg。
/// </summary>
internal static class MediaProbe
{
    private static readonly string[] FallbackDirs =
    {
        "D:/user/chisenin/download/Programs/ffmpeg-8.0.1-essentials_build/bin",
        "C:/LEL/LEL-Downloader/Source/ffmpeg",
    };

    public static string FindTool(string name)
    {
        // ★ v1.6.3：工具自装目录优先 —— 自动安装的 ffmpeg 放在
        //   ~/.xqd_tool/ffmpeg/bin，不写系统 PATH，靠这里接上。
        string self = Path.Combine(Setup.DependencyCheck.ToolFfmpegDir, name + ".exe");
        if (File.Exists(self)) return self;

        string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var raw in pathEnv.Split(Path.PathSeparator))
        {
            string dir = raw.Trim().Trim('"');
            if (dir.Length == 0) continue;
            try
            {
                string p = Path.Combine(dir, name + ".exe");
                if (File.Exists(p)) return p;
                p = Path.Combine(dir, name);
                if (File.Exists(p)) return p;
            }
            catch { /* 非法 PATH 项跳过 */ }
        }
        foreach (var baseDir in FallbackDirs)
        {
            string p = Path.Combine(baseDir, name + ".exe");
            if (File.Exists(p)) return p;
        }
        throw new InvalidOperationException("找不到 " + name + ".exe");
    }

    public static string FfmpegPath => FindTool("ffmpeg");
    public static string FfprobePath => FindTool("ffprobe");

    /// <summary>ffprobe 取时长（秒），失败返回 0。对应 probe_duration。</summary>
    public static double ProbeDuration(string path)
    {
        try
        {
            var r = Proc.Run(FfprobePath, new[]
            {
                "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", path,
            }, 180000);
            if (!r.Ok) return 0.0;
            return double.TryParse((r.Out ?? "").Trim(), NumberStyles.Any,
                                   CultureInfo.InvariantCulture, out var d) ? d : 0.0;
        }
        catch { return 0.0; }
    }

    /// <summary>
    /// 探测媒体真实容器与编码（对应 probe_media）。
    /// ★ AUDIO 直链必须靠 ffprobe 探真实容器：Content-Type 一律 audio/mpeg 不可信；
    ///   mjpeg 只是 MP3 内嵌封面，不算视频轨。
    /// </summary>
    public static MediaInfo ProbeMedia(string path)
    {
        var info = new MediaInfo();
        try
        {
            var r = Proc.Run(FfprobePath, new[]
            {
                "-v", "error", "-show_entries",
                "format=format_name,duration,size:stream=codec_type,codec_name",
                "-of", "json", path,
            }, 180000);
            if (!r.Ok) return info;

            using var doc = JsonDocument.Parse(r.Out ?? "");
            var root = doc.RootElement;

            if (root.TryGetProperty("format", out var fmt) && fmt.ValueKind == JsonValueKind.Object)
            {
                if (fmt.TryGetProperty("format_name", out var fn) && fn.ValueKind == JsonValueKind.String)
                    info.FormatName = fn.GetString() ?? "";
                if (fmt.TryGetProperty("duration", out var du))
                    info.Duration = ParseDouble(du);
                if (fmt.TryGetProperty("size", out var sz))
                    info.Size = ParseLong(sz);
            }

            if (root.TryGetProperty("streams", out var streams) &&
                streams.ValueKind == JsonValueKind.Array)
            {
                foreach (var s in streams.EnumerateArray())
                {
                    string codec = s.TryGetProperty("codec_name", out var cn) &&
                                   cn.ValueKind == JsonValueKind.String ? (cn.GetString() ?? "") : "";
                    string type = s.TryGetProperty("codec_type", out var ct) &&
                                  ct.ValueKind == JsonValueKind.String ? (ct.GetString() ?? "") : "";
                    info.Codecs.Add(codec);
                    if (type == "audio") info.HasAudio = true;
                    // 真实视频轨：排除 MP3 内嵌的 mjpeg 封面
                    if (type == "video" && !string.Equals(codec, "mjpeg",
                                                          StringComparison.OrdinalIgnoreCase))
                        info.HasVideo = true;
                }
            }
        }
        catch { /* 探测失败返回空信息，由 audio_ext_for 兜底 */ }
        return info;
    }

    /// <summary>按真实容器判定音频成品扩展名（对应 audio_ext_for）。</summary>
    public static string AudioExtFor(string path)
    {
        var info = ProbeMedia(path);
        var codecs = info.Codecs.Select(c => (c ?? "").ToLowerInvariant()).ToList();
        if (codecs.Contains("mp3") || codecs.Contains("mp3float")) return ".mp3";
        if (!info.HasVideo && (codecs.Contains("aac") || codecs.Contains("mp4a"))) return ".m4a";
        if ((info.FormatName ?? "").ToLowerInvariant().Contains("mp3")) return ".mp3";
        if (!info.HasVideo) return ".m4a";
        return ".mp3";
    }

    /// <summary>替换扩展名（对应 swap_ext）。</summary>
    public static string SwapExt(string path, string ext) => Path.ChangeExtension(path, ext);

    private static double ParseDouble(JsonElement e)
    {
        if (e.ValueKind == JsonValueKind.Number && e.TryGetDouble(out var d)) return d;
        if (e.ValueKind == JsonValueKind.String &&
            double.TryParse(e.GetString(), NumberStyles.Any,
                            CultureInfo.InvariantCulture, out var x)) return x;
        return 0.0;
    }

    private static long ParseLong(JsonElement e)
    {
        if (e.ValueKind == JsonValueKind.Number && e.TryGetInt64(out var n)) return n;
        if (e.ValueKind == JsonValueKind.String &&
            long.TryParse(e.GetString(), NumberStyles.Any,
                          CultureInfo.InvariantCulture, out var x)) return x;
        return 0L;
    }
}
