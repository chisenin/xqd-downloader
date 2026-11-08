using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core.Setup;

/// <summary>下载源。★ 排序即优先级，从上到下依次尝试。</summary>
public sealed class DepSource
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Url { get; set; } = "";
    /// <summary>压缩格式：gz（单文件）或 zip（整包）。</summary>
    public string Format { get; set; } = "gz";
    /// <summary>zip 包内的可执行文件路径模板（相对包内根）。</summary>
    public string InnerPath { get; set; } = "";

    public override string ToString() => Name;
}

/// <summary>下载进度回调参数。</summary>
public sealed class DepProgress
{
    public string SourceName { get; set; } = "";
    public long Total { get; set; }
    public long Done { get; set; }
    public string Stage { get; set; } = "";

    public int Percent => Total > 0 ? (int)Math.Min(100, Done * 100 / Total) : 0;
}

/// <summary>
/// ★ v1.6.3：ffmpeg / ffprobe 自动下载安装。
///
/// ## 下载源策略（用户要求：尽量不走 GitHub，走不通才用带代理的 GitHub）
///
/// 实测（2026-11-08，国内网络）：
/// | 源 | 类型 | 实测速度 | 结论 |
/// |---|---|---|---|
/// | registry.npmmirror.com（阿里 CDN） | **非 GitHub·国内** | ~200 KB/s | **首选** |
/// | www.gyan.dev（ffmpeg 官方 Windows 构建） | 非 GitHub | 100~370 KB/s | 备选 |
/// | ghfast.top | GitHub 代理 | ~185 KB/s | 兜底 |
/// | gh-proxy.com | GitHub 代理 | ~235 KB/s | 兜底 |
/// | ghproxy.net / 华为云 / 腾讯云 | — | 504 / 只有网页 / 404 | **不用** |
///
/// ## 为什么用 npmmirror 的 ffmpeg-static
/// 它提供**独立的 win32-x64 可执行文件**（`ffmpeg-win32-x64.gz` / `ffprobe-win32-x64.gz`），
/// .NET 用 `GZipStream` 原生就能解压 —— 不需要 tar / 7z / 任何外部工具。
/// （npmmirror 的 ffmpeg-builds 只有 .tar.xz，要靠外部 tar，不适合「一键安装」。）
///
/// ## 安装位置
/// `~/.xqd_tool/ffmpeg/bin/` —— **用户目录，不写 Program Files，不需要管理员权限**，
/// 也不污染系统 PATH。查找时优先级最高（见 DependencyCheck.FindTool）。
/// </summary>
public static class DependencyInstaller
{
    /// <summary>ffmpeg-static 的版本目录（对应 npm 的 ffmpeg-static 包版本）。</summary>
    private const string StaticVersion = "b6.1.1";

    /// <summary>
    /// 下载源列表（按优先级）。每项提供 ffmpeg 与 ffprobe 两个 URL。
    /// </summary>
    public static List<DepSource> FfmpegSources() => new List<DepSource>
    {
        // ① 首选：阿里 npmmirror —— 国内 CDN，不经 GitHub
        new DepSource
        {
            Id = "npmmirror",
            Name = "阿里云镜像（npmmirror，国内直连）",
            Url = $"https://registry.npmmirror.com/-/binary/ffmpeg-static/{StaticVersion}/{{0}}-win32-x64.gz",
            Format = "gz",
        },
        // ② 备选：ffmpeg 官方推荐的 Windows 构建站（gyan.dev），zip 整包
        new DepSource
        {
            Id = "gyan",
            Name = "ffmpeg 官方构建站（gyan.dev，海外）",
            Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
            Format = "zip",
            InnerPath = "bin",
        },
        // ③ 兜底：GitHub + 稳定代理（国内直连 GitHub 基本不通，必须走代理）
        new DepSource
        {
            Id = "ghfast",
            Name = "GitHub 加速（ghfast.top 代理）",
            Url = "https://ghfast.top/https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip",
            Format = "zip",
            InnerPath = "bin",
        },
        new DepSource
        {
            Id = "ghproxy",
            Name = "GitHub 加速（gh-proxy.com 代理）",
            Url = "https://gh-proxy.com/https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip",
            Format = "zip",
            InnerPath = "bin",
        },
    };

    /// <summary>下载单个工具（ffmpeg / ffprobe），返回落盘后的 exe 路径。失败返回 null。</summary>
    private static async Task<string> DownloadOneAsync(DepSource src, string tool,
                                                       string destDir, IProgress<DepProgress> progress,
                                                       CancellationToken ct)
    {
        string url = src.Format == "gz"
            ? string.Format(src.Url, tool)
            : src.Url;

        progress?.Report(new DepProgress
        {
            SourceName = src.Name,
            Stage = $"正在下载 {tool}（{src.Name}）",
        });

        var tmp = Path.Combine(Path.GetTempPath(),
            $"xqd_{tool}_{Guid.NewGuid():N}." + (src.Format == "gz" ? "gz" : "zip"));
        try
        {
            // ★ 用 Net.OpenStreamAsync：它已经禁用了系统代理（业务网关同款设置）。
            //   但下载走的是公共 CDN，系统代理反而有用 —— 所以这里单独建一个
            //   允许代理的 client：国内机器常配了公司代理/加速器。
            using var client = CreateDownloadClient();
            using var resp = await client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct)
                                         .ConfigureAwait(false);
            resp.EnsureSuccessStatusCode();
            long total = resp.Content.Headers.ContentLength ?? 0;

            using (var srcStream = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false))
            using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                var buf = new byte[128 * 1024];
                long done = 0;
                int n;
                while ((n = await srcStream.ReadAsync(buf, ct).ConfigureAwait(false)) > 0)
                {
                    await fs.WriteAsync(buf.AsMemory(0, n), ct).ConfigureAwait(false);
                    done += n;
                    progress?.Report(new DepProgress
                    {
                        SourceName = src.Name,
                        Total = total,
                        Done = done,
                        Stage = $"正在下载 {tool}（{src.Name}）",
                    });
                }
            }

            progress?.Report(new DepProgress
            {
                SourceName = src.Name, Total = total, Done = total,
                Stage = $"正在解压 {tool}",
            });

            Directory.CreateDirectory(destDir);
            string exePath = Path.Combine(destDir, tool + ".exe");
            if (src.Format == "gz")
            {
                // gzip 单文件 → 直接gunzip
                using (var gz = new GZipStream(File.OpenRead(tmp), CompressionMode.Decompress))
                using (var outFs = new FileStream(exePath, FileMode.Create, FileAccess.Write))
                    await gz.CopyToAsync(outFs, ct).ConfigureAwait(false);
            }
            else
            {
                // zip 整包 → 找出 ffmpeg.exe / ffprobe.exe（包内通常在 bin/ 下）
                using var zip = ZipFile.OpenRead(tmp);
                var entry = zip.Entries.FirstOrDefault(e =>
                    string.Equals(Path.GetFileName(e.FullName), tool + ".exe",
                                 StringComparison.OrdinalIgnoreCase));
                if (entry == null) throw new IOException("压缩包里没有 " + tool + ".exe");
                entry.ExtractToFile(exePath, true);
            }

            // 落盘后自检：能不能跑起来
            try
            {
                var r = Proc.Run(exePath, new[] { "-version" }, 20000);
                if (!r.Ok) throw new IOException(tool + " 自检失败（返回 " + r.Code + "）");
            }
            catch (Exception e) when (e is IOException)
            {
                throw;
            }
            catch (Exception e)
            {
                throw new IOException(tool + " 自检失败：" + e.Message);
            }
            return exePath;
        }
        finally
        {
            try { if (File.Exists(tmp)) File.Delete(tmp); } catch { /* ignore */ }
        }
    }

    /// <summary>
    /// 下载并安装 ffmpeg + ffprobe。逐个源尝试，第一个成功的即返回。
    /// </summary>
    /// <param name="progress">进度回调（可空）。</param>
    /// <param name="ct">取消令牌。</param>
    /// <returns>安装结果：成功返回两条 exe 路径；全部失败返回错误说明。</returns>
    public static async Task<(bool Ok, string Message, string Ffmpeg, string Ffprobe)>
        InstallFfmpegAsync(IProgress<DepProgress> progress = null, CancellationToken ct = default)
    {
        var sources = FfmpegSources();
        var errors = new List<string>();

        foreach (var src in sources)
        {
            try
            {
                ct.ThrowIfCancellationRequested();
                progress?.Report(new DepProgress { SourceName = src.Name, Stage = "准备从 " + src.Name + " 下载" });

                string dir = DependencyCheck.ToolFfmpegDir;
                string ff = await DownloadOneAsync(src, "ffmpeg", dir, progress, ct).ConfigureAwait(false);
                string fp = await DownloadOneAsync(src, "ffprobe", dir, progress, ct).ConfigureAwait(false);

                progress?.Report(new DepProgress
                {
                    SourceName = src.Name, Stage = "安装完成",
                });
                return (true, "已从 " + src.Name + " 安装 ffmpeg 与 ffprobe", ff, fp);
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception e)
            {
                errors.Add(src.Name + "：" + e.Message);
                // 换下一个源
            }
        }

        return (false,
            "所有下载源都失败了：\n· " + string.Join("\n· ", errors),
            null, null);
    }

    /// <summary>
    /// 下载用的 HttpClient：**允许**系统代理。
    /// 与 Net 的业务客户端相反 —— 业务网关必须禁代理（否则被吞成 HTML），
    /// 但公共 CDN 走代理/加速器往往更快，甚至本机根本不通直连。
    /// </summary>
    private static HttpClient CreateDownloadClient()
    {
        var handler = new HttpClientHandler
        {
            AllowAutoRedirect = true,
            AutomaticDecompression = System.Net.DecompressionMethods.All,
        };
        // 不主动 UseProxy=false —— 尊重系统设置（国内机器常配代理）
        var c = new HttpClient(handler) { Timeout = TimeSpan.FromMinutes(20) };
        c.DefaultRequestHeaders.TryAddWithoutValidation("User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36");
        return c;
    }
}
