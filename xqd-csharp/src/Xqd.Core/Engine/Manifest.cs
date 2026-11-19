using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core.Engine;

/// <summary>清单种类，对应 xqd_engine.parse_manifest 的 kind。</summary>
internal enum ManifestKind
{
    Media,
    Master,
    Drm,
    Direct,
}

/// <summary>一个 HLS 分片：URL + EXTINF 时长（秒）。</summary>
internal sealed class Segment
{
    public string Url { get; set; } = "";
    public double Duration { get; set; }

    public Segment() { }
    public Segment(string url, double duration) { Url = url; Duration = duration; }
}

/// <summary>parse_manifest 的结果：(segments, kind, note, total_seconds)。</summary>
internal sealed class ManifestInfo
{
    public List<Segment> Segments { get; set; } = new List<Segment>();
    public ManifestKind Kind { get; set; } = ManifestKind.Media;
    public string Note { get; set; } = "";
    public double TotalDuration { get; set; }
    /// <summary>分片相对路径所基于的清单 URL（master 子清单 / drm 明文孪生）。</summary>
    public string SourceUrl { get; set; } = "";
}

/// <summary>
/// 清单解析 —— 对应 xqd_engine.parse_manifest / _parse_media_manifest。
///
/// 分派规则（docs/01 七节，全部实测过，不改）：
///   含 EXT-X-KEY        → drm   ：找同目录明文孪生，必须做时长校验
///   含 EXT-X-STREAM-INF → master：按短边 min(w,h) 选最清晰（这批课多竖屏）
///   其余                → media ：直接下载
///   非 #EXTM3U 正文      → direct：直链媒体（AUDIO 类）
///
/// ★ 明文课(master)绝不能走孪生（时长不符会下错内容）。
/// ★ DRM 孪生容差 max(1.0, want*0.005)；请求孪生必须去掉 encdomain=cmv1，否则 403。
/// ★ sign 只绑定目录和 t、不绑定文件名 → 同目录其它文件复用同一个 sign；
///   目录是 host/appId/&lt;8hex&gt;&lt;bizFileId&gt;/&lt;file&gt; 三层，等价 rsplit('/', 2)。
/// </summary>
internal static class ManifestParser
{
    private static readonly byte[] ExtM3U = Encoding.ASCII.GetBytes("#EXTM3U");
    private static readonly Regex ExtinfTotalRe = new(@"#EXTINF:([\d.]+)", RegexOptions.Compiled);
    private static readonly Regex DurRe = new(@"([0-9.]+)", RegexOptions.Compiled);
    private static readonly Regex ResRe = new(@"RESOLUTION=([0-9]+x[0-9]+)", RegexOptions.Compiled);
    private static readonly Regex ShortSideRe = new(@"(\d+)x(\d+)", RegexOptions.Compiled);
    private static readonly Regex VideoNumRe = new(@"video_(\d+)_", RegexOptions.Compiled);
    private static readonly Regex TwinNameRe = new(@"v\.f(\d+)\.m3u8", RegexOptions.Compiled);

    private sealed class Variant
    {
        public string Res = "";
        public string Url = "";
        public int Short;
    }

    public static async Task<ManifestInfo> ParseAsync(string url, string quality, CancellationToken ct)
    {
        byte[] body;
        try
        {
            // 所有 CDN/网关请求走 Net（禁用系统代理）
            body = await Net.GetBytesAsync(url, 30, null, ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception e) { return Failed("清单拉取失败 (" + e.Message + ")"); }

        // 直链媒体：正文不是 m3u8（AUDIO 类课程，URL 后缀会骗人，容器靠 ffprobe 探）
        if (!StartsWithExtM3U(body))
        {
            var info = new ManifestInfo
            {
                Kind = ManifestKind.Direct,
                Note = "直链媒体",
                SourceUrl = url,
            };
            info.Segments.Add(new Segment(url, 0));
            return info;
        }

        string text = Encoding.UTF8.GetString(body);

        // 与 xqd_engine.parse_manifest 一致：先判 master，再判 drm。
        // 实测一份清单不会同时含 STREAM-INF 与 KEY，顺序不影响结果。
        if (text.IndexOf("EXT-X-STREAM-INF", StringComparison.Ordinal) >= 0)
            return await ParseMasterAsync(text, url, quality, ct).ConfigureAwait(false);

        if (text.IndexOf("#EXT-X-KEY", StringComparison.Ordinal) >= 0)
            return await ParseDrmAsync(text, url, ct).ConfigureAwait(false);

        return Parsed(ParseMediaManifest(text, url), ManifestKind.Media, "标准 HLS", url);
    }

    /// <summary>master：选一路子清单（短边最大 / 或按 quality 取 >= want 的最小一路）。</summary>
    private static async Task<ManifestInfo> ParseMasterAsync(string text, string url,
                                                             string quality, CancellationToken ct)
    {
        var lines = text.Split('\n').Select(l => l.Trim()).ToList();
        var variants = new List<Variant>();
        for (int i = 0; i < lines.Count; i++)
        {
            if (!lines[i].StartsWith("#EXT-X-STREAM-INF", StringComparison.Ordinal)) continue;
            var m = ResRe.Match(lines[i]);
            string res = m.Success ? m.Groups[1].Value : "";
            for (int j = i + 1; j < lines.Count; j++)
            {
                string refLine = lines[j];
                if (refLine.Length > 0 && !refLine.StartsWith("#", StringComparison.Ordinal))
                {
                    variants.Add(new Variant { Res = res, Url = refLine, Short = ShortSide(res) });
                    break;
                }
            }
        }
        if (variants.Count == 0) return Failed("master 清单没有可用码率");

        // ★ 按短边 min(w,h) 排序：这批课多为竖屏（480x852 / 720x1280），看高度会误选最差一路
        variants = variants.OrderBy(v => v.Short).ToList();

        string q = string.IsNullOrEmpty(quality) ? "max" : quality;
        Variant pick;
        if (string.Equals(q, "max", StringComparison.OrdinalIgnoreCase))
        {
            pick = variants[variants.Count - 1];
        }
        else
        {
            int want = int.TryParse(q, NumberStyles.Any, CultureInfo.InvariantCulture, out var w) ? w : 720;
            pick = variants[variants.Count - 1];
            foreach (var v in variants)
                if (v.Short >= want) { pick = v; break; }
        }

        string directory = DirOf(url);
        string src = pick.Url;
        if (!src.StartsWith("http", StringComparison.OrdinalIgnoreCase))
        {
            // sign 只绑目录、不绑文件名：子清单行没带 query 时继承 master 的 query
            if (src.IndexOf('?') < 0 && url.IndexOf('?') >= 0)
                src += url.Substring(url.IndexOf('?'));
            src = directory + src;
        }

        byte[] sub;
        try { sub = await Net.GetBytesAsync(src, 30, null, ct).ConfigureAwait(false); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception e) { return Failed("子清单拉取失败 (" + e.Message + ")"); }
        if (!StartsWithExtM3U(sub)) return Failed("子清单拉取失败 (非 m3u8)");

        return Parsed(ParseMediaManifest(Encoding.UTF8.GetString(sub), src),
                      ManifestKind.Master, "多码率 " + pick.Res, src);
    }

    /// <summary>
    /// drm：找同目录明文孪生（绕开 DRM）。
    /// voddrm.token.&lt;JWT&gt;.video_1440285_0.m3u8 → v.f1440285.m3u8（编号一致）。
    /// ★ 必须做时长校验，否则同目录里别路视频（实测有 2.8 小时其它内容）会下错。
    /// </summary>
    private static async Task<ManifestInfo> ParseDrmAsync(string text, string url, CancellationToken ct)
    {
        string num = ExtractTwinNum(url) ?? ExtractTwinNum(text);
        if (num == null) return Failed("无法从 URL 推断孪生编号");

        var (path, query) = Util.SplitQuery(url);
        int slash = path.LastIndexOf('/');
        if (slash < 0) return Failed("URL 目录层级不足");
        // 等价 Python split_dir_query 的 rsplit('/', 2)：保留 host/appId/<8hex><bizFileId>/ 三层
        string directory = path.Substring(0, slash + 1);

        // ★ 请求明文孪生模板必须去掉 encdomain=cmv1，否则 403；
        //   sign 只绑目录和 t、不绑文件名 → 同目录其它文件复用同一个 sign。
        string twin = directory + "v.f" + num + ".m3u8" + Util.QueryWithout(query, "encdomain");

        byte[] body;
        try { body = await Net.GetBytesAsync(twin, 30, null, ct).ConfigureAwait(false); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception e) { return Failed("明文孪生拉取失败 (" + e.Message + ")"); }
        if (!StartsWithExtM3U(body)) return Failed("明文孪生拉取失败 (非 m3u8)");

        string t = Encoding.UTF8.GetString(body);
        if (t.IndexOf("EXT-X-KEY", StringComparison.Ordinal) >= 0)
            return Failed("明文孪生仍是加密清单");

        double want = ExtinfTotal(text);   // DRM 清单标称总时长
        double got = ExtinfTotal(t);       // 孪生清单标称总时长
        double tol = Math.Max(1.0, want * 0.005);
        if (want > 0 && (got <= 0 || Math.Abs(got - want) > tol))
            return Failed("明文孪生时长不符：" + got.ToString("0.0", CultureInfo.InvariantCulture)
                          + "s vs 期望 " + want.ToString("0.0", CultureInfo.InvariantCulture) + "s");

        return Parsed(ParseMediaManifest(t, twin), ManifestKind.Drm, "加密清单（明文孪生）", twin);
    }

    /// <summary>媒体清单 → [(url, dur)]，保持顺序（对应 _parse_media_manifest）。</summary>
    private static List<Segment> ParseMediaManifest(string text, string baseUrl)
    {
        string directory = DirOf(baseUrl);
        var segs = new List<Segment>();
        double cur = 0.0;
        foreach (var raw in text.Split('\n'))
        {
            string line = raw.Trim();
            if (line.Length == 0) continue;
            if (line.StartsWith("#EXTINF:", StringComparison.Ordinal))
            {
                var m = DurRe.Match(line);
                cur = m.Success && double.TryParse(m.Groups[1].Value, NumberStyles.Any,
                          CultureInfo.InvariantCulture, out var d) ? d : 0.0;
            }
            else if (line.StartsWith("#", StringComparison.Ordinal)) continue;
            else
            {
                string full = line.StartsWith("http", StringComparison.OrdinalIgnoreCase)
                              ? line : directory + line;
                segs.Add(new Segment(full, cur));
                cur = 0.0;
            }
        }
        return segs;
    }

    /// <summary>清单标称总时长（对应 xqd_app._extinf_total）。</summary>
    private static double ExtinfTotal(string text)
    {
        double total = 0.0;
        foreach (Match m in ExtinfTotalRe.Matches(text))
            if (double.TryParse(m.Groups[1].Value, NumberStyles.Any,
                                CultureInfo.InvariantCulture, out var v))
                total += v;
        return total;
    }

    /// <summary>RESOLUTION 的短边 min(w,h)，用于竖屏课选流。</summary>
    private static int ShortSide(string res)
    {
        var m = ShortSideRe.Match(res ?? "");
        if (!m.Success) return 0;
        int w = int.TryParse(m.Groups[1].Value, NumberStyles.Any,
                             CultureInfo.InvariantCulture, out var a) ? a : 0;
        int h = int.TryParse(m.Groups[2].Value, NumberStyles.Any,
                             CultureInfo.InvariantCulture, out var b) ? b : 0;
        return Math.Min(w, h);
    }

    /// <summary>从 URL 或清单正文推断孪生编号：video_&lt;num&gt;_ 或 v.f&lt;num&gt;.m3u8。</summary>
    private static string ExtractTwinNum(string s)
    {
        if (string.IsNullOrEmpty(s)) return null;
        var m = VideoNumRe.Match(s);
        if (!m.Success) m = TwinNameRe.Match(s);
        return m.Success ? m.Groups[1].Value : null;
    }

    /// <summary>url.rsplit('/', 1)[0] + '/' —— 保留目录部分（先去掉 query 更稳）。</summary>
    private static string DirOf(string url)
    {
        var (path, _) = Util.SplitQuery(url);
        int i = path.LastIndexOf('/');
        return i >= 0 ? path.Substring(0, i + 1) : "";
    }

    private static bool StartsWithExtM3U(byte[] b)
    {
        if (b == null || b.Length < ExtM3U.Length) return false;
        for (int i = 0; i < ExtM3U.Length; i++)
            if (b[i] != ExtM3U[i]) return false;
        return true;
    }

    private static ManifestInfo Failed(string note) => new ManifestInfo { Note = note };

    private static ManifestInfo Parsed(List<Segment> segs, ManifestKind kind,
                                       string note, string srcUrl)
    {
        double total = 0.0;
        foreach (var s in segs) total += s.Duration;
        return new ManifestInfo
        {
            Segments = segs,
            Kind = kind,
            Note = note,
            TotalDuration = total,
            SourceUrl = srcUrl,
        };
    }
}
