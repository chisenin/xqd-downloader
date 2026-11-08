using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Xqd.Core;

namespace Xqd.Core.Adb;

/// <summary>
/// 链接 / 清单 / 明文孪生 / 码率选择 / 下载助手 —— 对照 xqd_app.py 的
/// split_dir_query / query_without / http_get / classify_manifest / find_plain_twin /
/// safe_name / _pick_variant / download / probe_alive。
///
/// 已验证事实（docs/01 六/七节）：
///  · sign 只绑目录和 t、不绑文件名 → 同目录其它文件复用同一个 sign。
///  · t 相对服务器时钟约 4.8h 偏移 → 不用本地时间推算，probe_alive 用 HTTP 200/403 实探。
///  · 请求明文孪生模板必须去掉 encdomain=cmv1，否则 403。
///  · 目录三层 host/appId/&lt;8hex&gt;&lt;bizFileId&gt;/&lt;file&gt; 用 rsplit('/',2) 等价处理。
///  · DRM 清单 voddrm.token.&lt;JWT&gt;.video_1440285_0.m3u8 → v.f1440285.m3u8（编号一致），
///    必须时长校验，容差 max(1.0, want*0.005)，否则会下到同目录 2.8 小时的其它内容。
///  · master 多为竖屏（480x852/720x1280），清晰度看短边 min(w,h)；明文课(master)不能走孪生。
/// </summary>
internal static class LinkOps
{
    // 禁用系统代理 + TLS 校验关闭，复用 Net.CreateClient（对应 Python ProxyHandler({})/CERT_NONE）。
    private static readonly HttpClient Http = Net.CreateClient();

    private static readonly byte[] ExtM3U = Encoding.ASCII.GetBytes("#EXTM3U");
    private static readonly Regex ExtinfRe = new(@"#EXTINF:([\d.]+)", RegexOptions.Compiled);
    private static readonly Regex ResRe = new(@"RESOLUTION=(\d+x\d+)", RegexOptions.Compiled);
    private static readonly Regex ShortSideRe = new(@"(\d+)x(\d+)", RegexOptions.Compiled);
    private static readonly Regex VideoNumRe = new(@"video_(\d+)_", RegexOptions.Compiled);
    private static readonly Regex TwinNameRe = new(@"v\.f(\d+)\.m3u8", RegexOptions.Compiled);
    private static readonly Regex IllegalRe = new(@"[\\/:*?""<>|\r\n\t]", RegexOptions.Compiled);

    // Python TWIN_RANGES = [(1440280, 1440300)]
    private const int TwinLo = 1440280, TwinHi = 1440300;

    private static readonly HashSet<string> Reserved = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    };

    // ── http_get：返回 (status, body)，非 200 不抛（对应 Python 返回 (None, str(e))） ──

    public static async Task<(int code, byte[] body)> HttpGetAsync(
        string url, int timeoutSeconds = 25, CancellationToken ct = default)
    {
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, url);
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
            using var resp = await Http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead,
                                                  cts.Token).ConfigureAwait(false);
            var bytes = await resp.Content.ReadAsByteArrayAsync(cts.Token).ConfigureAwait(false);
            return ((int)resp.StatusCode, bytes);
        }
        catch (Exception e)
        {
            return (0, Encoding.UTF8.GetBytes(e.Message));
        }
    }

    // ── URL 拆分 ───────────────────────────────────────────────────

    /// <summary>
    /// 拆 URL → (目录, 文件名, 查询串)。目录含 host/appId/&lt;8hex&gt;&lt;biz&gt;/ 三层，
    /// 等价 Python url.rsplit('/', 2) 后 parts[0]+'/'+parts[1]+'/'。
    /// query 不含前导 '?'（与 Python partition('?') 一致）。
    /// </summary>
    public static (string dir, string file, string query) SplitDirQuery(string url)
    {
        var (path, query) = Util.SplitQuery(url);
        int i1 = path.LastIndexOf('/');
        if (i1 <= 0) return ("", "", query);              // 目录层级不足
        int i2 = path.LastIndexOf('/', i1 - 1);
        if (i2 < 0) return ("", "", query);
        return (path.Substring(0, i1 + 1), path.Substring(i1 + 1), query);
    }

    /// <summary>去掉指定查询参数，返回不带前导 '?' 的串（Python query_without 语义）。</summary>
    public static string QueryWithout(string query, params string[] drop)
    {
        if (string.IsNullOrEmpty(query)) return "";
        var kept = new List<string>();
        foreach (var kv in query.Split('&'))
        {
            if (kv.Length == 0) continue;
            var name = kv.Split('=')[0];
            bool skip = false;
            foreach (var d in drop)
                if (string.Equals(name, d, StringComparison.OrdinalIgnoreCase)) { skip = true; break; }
            if (!skip) kept.Add(kv);
        }
        return string.Join("&", kept);
    }

    /// <summary>清单标称总时长（对应 xqd_app._extinf_total）。</summary>
    public static double ExtinfTotal(string text)
    {
        double total = 0.0;
        foreach (Match m in ExtinfRe.Matches(text ?? ""))
            if (double.TryParse(m.Groups[1].Value, NumberStyles.Any,
                                CultureInfo.InvariantCulture, out var v))
                total += v;
        return total;
    }

    private static bool StartsWithExtM3U(byte[] b)
    {
        if (b == null || b.Length < ExtM3U.Length) return false;
        for (int i = 0; i < ExtM3U.Length; i++)
            if (b[i] != ExtM3U[i]) return false;
        return true;
    }

    private static string ExtractTwinNum(string s)
    {
        if (string.IsNullOrEmpty(s)) return null;
        var m = VideoNumRe.Match(s);
        if (!m.Success) m = TwinNameRe.Match(s);
        return m.Success ? m.Groups[1].Value : null;
    }

    // ── 清单类型分派（docs/01 七节） ───────────────────────────────

    /// <summary>取清单正文并判类型：master / drm / media；取不到返回 kind=null。</summary>
    public static async Task<(string kind, string text)> ClassifyManifestAsync(
        string url, int timeoutSeconds = 25, CancellationToken ct = default)
    {
        var (code, body) = await HttpGetAsync(url, timeoutSeconds, ct).ConfigureAwait(false);
        if (code != 200) return (null, "");
        var text = Encoding.UTF8.GetString(body);
        if (text.IndexOf("EXT-X-STREAM-INF", StringComparison.Ordinal) >= 0) return ("master", text);
        if (text.IndexOf("EXT-X-KEY", StringComparison.Ordinal) >= 0) return ("drm", text);
        return ("media", text);
    }

    /// <summary>
    /// 在 DRM 清单同目录找明文孪生，要求「总时长一致」才同源。
    ///  · 编号一致优先（video_1440285_0 → v.f1440285.m3u8），保留 Python 的 TWIN_RANGES 兜底。
    ///  · 请求孪生去掉 encdomain=cmv1；sign 只绑目录和 t → 同目录复用。
    ///  · 容差 max(1.0, want*0.005)，杜绝下到同目录别路视频。
    /// </summary>
    public static async Task<string> FindPlainTwinAsync(string drmText, string url,
                                                        CancellationToken ct = default)
    {
        var (dir, _, query) = SplitDirQuery(url);
        if (string.IsNullOrEmpty(dir)) return null;
        double want = ExtinfTotal(drmText);
        if (want <= 0) return null;
        double tol = Math.Max(1.0, want * 0.005);
        string q2 = QueryWithout(query, "encdomain");    // ★ 去掉 encdomain=cmv1

        var candidates = new List<string>();
        var num = ExtractTwinNum(url) ?? ExtractTwinNum(drmText);
        if (num != null) candidates.Add("v.f" + num + ".m3u8");
        for (int n = TwinLo; n < TwinHi; n++)
        {
            var name = "v.f" + n + ".m3u8";
            if (!candidates.Contains(name)) candidates.Add(name);
        }

        foreach (var name in candidates)
        {
            string twin = dir + name + "?" + q2;        // sign 复用同目录
            var (code, body) = await HttpGetAsync(twin, 15, ct).ConfigureAwait(false);
            if (code != 200 || !StartsWithExtM3U(body)) continue;
            var t = Encoding.UTF8.GetString(body);
            if (t.IndexOf("EXT-X-KEY", StringComparison.Ordinal) >= 0) continue; // 仍是加密清单
            double got = ExtinfTotal(t);
            if (got > 0 && Math.Abs(got - want) < tol) return twin;   // ★ 时长校验
        }
        return null;
    }

    /// <summary>
    /// master 清单 → 子清单 URL 列表（按分辨率从低到高的基础数据）。
    /// 对应 xqd_app._pick_variant。
    /// </summary>
    public static List<(string res, string url)> PickVariant(string text, string directory, string query)
    {
        var outList = new List<(string res, string url)>();
        var lines = text.Split('\n').Select(l => l.Trim()).ToList();
        for (int i = 0; i < lines.Count; i++)
        {
            if (!lines[i].StartsWith("#EXT-X-STREAM-INF", StringComparison.Ordinal)) continue;
            string res = "";
            var m = ResRe.Match(lines[i]);
            if (m.Success) res = m.Groups[1].Value;
            for (int j = i + 1; j < lines.Count; j++)
            {
                var refLine = lines[j];
                if (refLine.Length == 0 || refLine.StartsWith("#", StringComparison.Ordinal)) continue;
                var url = refLine.IndexOf('?') >= 0 ? refLine : refLine + "?" + query;
                outList.Add((res, directory + url));
                break;
            }
        }
        return outList;
    }

    /// <summary>RESOLUTION 的短边 min(w,h)：这批课多竖屏，看短边才不会误选最差一路。</summary>
    public static int ShortSide(string res)
    {
        var m = ShortSideRe.Match(res ?? "");
        if (!m.Success) return 0;
        int w = int.TryParse(m.Groups[1].Value, NumberStyles.Any,
                             CultureInfo.InvariantCulture, out var a) ? a : 0;
        int h = int.TryParse(m.Groups[2].Value, NumberStyles.Any,
                             CultureInfo.InvariantCulture, out var b) ? b : 0;
        return Math.Min(w, h);
    }

    /// <summary>HTTP 200/403 实探清单是否仍有效（不用本地时间推算 t）。对应 xqd_app.probe_alive。</summary>
    public static async Task<bool> ProbeAliveAsync(string url, int timeoutSeconds = 15,
                                                   CancellationToken ct = default)
    {
        var (code, body) = await HttpGetAsync(url, timeoutSeconds, ct).ConfigureAwait(false);
        return code == 200 && StartsWithExtM3U(body);
    }

    /// <summary>
    /// xqd_app.safe_name 的忠实版（maxlen=90，保留全角冒号「：」）。
    /// ★ C# 公共契约 Naming.SafeName 是全项目的单一事实来源；此处仅为旧路径对照保留，
    ///   不替代 Naming。
    /// </summary>
    public static string SafeName(string s, int maxlen = 90)
    {
        s = IllegalRe.Replace(s ?? "", "_").Trim().TrimEnd('.');
        if (s.Length > maxlen) s = s.Substring(0, maxlen);
        if (s.Length == 0) s = "未命名";
        var first = s.Split('.')[0].ToUpperInvariant();
        if (Reserved.Contains(first)) s = "_" + s;
        return s;
    }

    // ── download（旧路径独立下载器，对照 xqd_app.download） ─────────
    //
    // 说明：C# 主链路的下载走 Engine.DownloadEngine + Engine.ManifestParser
    //（其中已独立实现同样的孪生/master 分派）；本方法是 xqd_app.download 的
    // 忠实移植，供旧路径单独使用，不走 Python 互操作。

    private static string FfOutPath(string outPath)
    {
        var baseName = Path.GetFileName(outPath);
        var stem = baseName.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase)
            ? baseName.Substring(0, baseName.Length - 4) : baseName;
        // ★ 临时输出必须以 .mp4 结尾，否则 ffmpeg 认不出封装格式
        return Path.Combine(Path.GetDirectoryName(outPath) ?? "", stem + ".part.mp4");
    }

    private static string FindFfmpeg()
    {
        foreach (var c in new[] { @"C:\ffmpeg\bin\ffmpeg.exe",
                                  @"D:\Program Files\ffmpeg\bin\ffmpeg.exe" })
            if (File.Exists(c)) return c;
        return "ffmpeg";                              // 交给 Proc 按 PATH 解析
    }

    /// <summary>
    /// 按清单类型分派后转封装下载：drm → 明文孪生（时长校验）；
    /// master → 按短边选一路；media → 直连。返回 (ok, note, 百分比)。
    /// </summary>
    public static async Task<(bool ok, string note, double pct)> DownloadAsync(
        string url, string outPath, double totalSeconds = 0, string quality = "max",
        CancellationToken ct = default)
    {
        var (kind, text) = await ClassifyManifestAsync(url, 25, ct).ConfigureAwait(false);
        if (kind == null) return (false, "清单已失效（签名过期），需重新采集链接", 0);

        string src = url;
        string note = kind == "master" ? "多码率直连" : kind == "media" ? "明文直连" : "DRM 原链";
        double dur = ExtinfTotal(text);

        if (kind == "drm")
        {
            var twin = await FindPlainTwinAsync(text, url, ct).ConfigureAwait(false);
            if (twin == null) return (false, "未找到同源明文孪生，无法导出", 0);
            src = twin; note = "明文孪生";
            var (c2, b2) = await HttpGetAsync(twin, 15, ct).ConfigureAwait(false);
            if (c2 == 200) dur = ExtinfTotal(Encoding.UTF8.GetString(b2));
        }
        else if (kind == "master")
        {
            var (dir, _, query) = SplitDirQuery(url);
            var variants = PickVariant(text, dir, query);
            if (variants.Count == 0) return (false, "master 清单没有可用码率", 0);
            variants = variants.OrderBy(v => ShortSide(v.res)).ToList();   // ★ 短边排序
            string q = string.IsNullOrEmpty(quality) ? "max" : quality;
            (string res, string url) pick;
            if (string.Equals(q, "max", StringComparison.OrdinalIgnoreCase))
            {
                pick = variants[variants.Count - 1];                       // 短边最大
            }
            else
            {
                int want = int.TryParse(q, NumberStyles.Any, CultureInfo.InvariantCulture,
                                        out var w) ? w : 720;
                pick = variants[variants.Count - 1];
                foreach (var v in variants)
                    if (ShortSide(v.res) >= want) { pick = v; break; }     // 取 >=want 里最小一路
            }
            src = pick.url; note = "多码率 " + pick.res;
            var (c2, b2) = await HttpGetAsync(src, 20, ct).ConfigureAwait(false);
            if (c2 == 200) dur = ExtinfTotal(Encoding.UTF8.GetString(b2));
        }

        if (totalSeconds <= 0) totalSeconds = dur;

        string tmp = FfOutPath(outPath);
        var args = new[]
        {
            "-y", "-loglevel", "error",
            "-protocol_whitelist", "file,http,https,tcp,tls,crypto,httpproxy",
            "-progress", "pipe:1", "-nostats",
            "-i", src, "-c", "copy", "-bsf:a", "aac_adtstoasc",
            "-movflags", "+faststart", tmp,
        };
        // 所有子进程走 Proc（无窗 + 环境净化）
        var r = await Task.Run(() => Proc.Run(FindFfmpeg(), args, 3600000), ct)
                          .ConfigureAwait(false);

        double pct = 0;
        foreach (var raw in (r.Out ?? "").Split('\n'))
        {
            var line = raw.Trim();
            if (!line.StartsWith("out_time_ms=", StringComparison.Ordinal)) continue;
            if (long.TryParse(line.Substring("out_time_ms=".Length), out var us) && totalSeconds > 0)
                pct = Math.Min(99.5, us / 1e6 / totalSeconds * 100);
        }

        if (r.Ok && File.Exists(tmp) && new FileInfo(tmp).Length > 100000)
        {
            if (File.Exists(outPath)) File.Delete(outPath);
            File.Move(tmp, outPath);
            return (true, note, 100.0);
        }

        string err = string.IsNullOrEmpty(r.Err)
            ? "rc=" + r.Code
            : (r.Err.Length > 300 ? r.Err.Substring(r.Err.Length - 300) : r.Err);
        try { if (File.Exists(tmp)) File.Delete(tmp); } catch { /* ignore */ }
        return (false, note + ": " + err, pct);
    }
}
