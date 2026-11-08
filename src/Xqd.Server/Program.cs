using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Threading.Tasks;
using Xqd.Core;

namespace Xqd.Server;

/// <summary>
/// 兴趣岛课程导出 —— 本地网页版服务。对照 xqd_server.py 的 Handler / main。
/// 只用 BCL：HttpListener + System.Text.Json + 文件 IO；不含任何 Python 互操作。
/// </summary>
public static class Program
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,   // 等价 ensure_ascii=False
        WriteIndented = false,
    };

    public static async Task Main(string[] args)
    {
        int port = 8765;
        string mode = "api";
        string outRoot = Config.EffectiveOutDir(Config.Load());
        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--port":
                    if (i + 1 < args.Length && int.TryParse(args[++i], out var p) && p > 0) port = p;
                    break;
                case "--mode":
                    if (i + 1 < args.Length) mode = args[++i];
                    break;
                case "--out":
                    if (i + 1 < args.Length) outRoot = args[++i];
                    break;
            }
        }
        if (mode != "api" && mode != "adb") mode = "api";
        Directory.CreateDirectory(outRoot);

        var state = new ServerState(outRoot, mode);
        var actions = new ServerActions(state, mode, Config.Load());

        Console.WriteLine("数据源：" + (mode == "api" ? "API 直连（不需要模拟器）" : "模拟器（ADB）"));
        Console.WriteLine();
        Console.WriteLine("  兴趣岛课程导出工具已启动");
        Console.WriteLine($"  http://127.0.0.1:{port}/");
        Console.WriteLine("  输出目录：" + outRoot);
        Console.WriteLine();

        using var listener = new HttpListener();
        listener.Prefixes.Add($"http://127.0.0.1:{port}/");   // 仅本机回环，不绑 0.0.0.0
        listener.Start();
        while (true)
        {
            HttpListenerContext ctx;
            try { ctx = await listener.GetContextAsync().ConfigureAwait(false); }
            catch (HttpListenerException) { break; }
            catch (ObjectDisposedException) { break; }
            // 每个连接独立处理；下载在后台任务里跑，不阻塞 HTTP 响应。
            _ = Task.Run(() => HandleAsync(ctx, state, actions));
        }
    }

    private static async Task HandleAsync(HttpListenerContext ctx, ServerState state,
                                          ServerActions actions)
    {
        try
        {
            var req = ctx.Request;
            var path = req.Url?.AbsolutePath ?? "/";
            if (string.Equals(req.HttpMethod, "GET", StringComparison.OrdinalIgnoreCase))
                await HandleGetAsync(ctx, path, req.Url?.Query ?? "", state, actions)
                    .ConfigureAwait(false);
            else if (string.Equals(req.HttpMethod, "POST", StringComparison.OrdinalIgnoreCase))
                await HandlePostAsync(ctx, path, state, actions).ConfigureAwait(false);
            else
                await SendJsonAsync(ctx, 404, Err("not found")).ConfigureAwait(false);
        }
        catch (Exception e)
        {
            try
            {
                await SendJsonAsync(ctx, 500, new Dictionary<string, object>
                {
                    ["error"] = e.Message,
                    ["trace"] = ServerState.Tail(e.ToString(), 800),
                }).ConfigureAwait(false);
            }
            catch { /* 响应可能已写出，忽略 */ }
        }
        finally
        {
            try { ctx.Response.Close(); } catch { }
        }
    }

    // ── GET 路由（路径与 ui.html 的 fetch 完全一致）──
    private static async Task HandleGetAsync(HttpListenerContext ctx, string path, string rawQuery,
                                             ServerState state, ServerActions actions)
    {
        var q = ParseQuery(rawQuery);
        switch (path)
        {
            case "/":
            case "/index.html":
                await SendUiAsync(ctx).ConfigureAwait(false);
                return;

            case "/api/state":
                await SendJsonAsync(ctx, 200, state.Snapshot()).ConfigureAwait(false);
                return;

            case "/api/camps":
                await SendJsonAsync(ctx, 200,
                    await actions.ListCampsAsync(Q(q, "tab") ?? "全部").ConfigureAwait(false))
                    .ConfigureAwait(false);
                return;

            case "/api/courses":
            {
                var camp = Q(q, "camp") ?? "";
                if (camp.Length == 0)
                {
                    await SendJsonAsync(ctx, 400, Err("缺少 camp")).ConfigureAwait(false);
                    return;
                }
                await SendJsonAsync(ctx, 200,
                    await actions.CatalogAsync(camp).ConfigureAwait(false)).ConfigureAwait(false);
                return;
            }

            case "/api/files":
                await SendJsonAsync(ctx, 200, actions.Files(Q(q, "camp"))).ConfigureAwait(false);
                return;

            default:
                if (path.StartsWith("/api/", StringComparison.Ordinal))
                {
                    await SendJsonAsync(ctx, 404, Err("not found")).ConfigureAwait(false);
                    return;
                }
                await ServeStaticAsync(ctx, path).ConfigureAwait(false);
                return;
        }
    }

    // ── POST 路由 ──
    private static async Task HandlePostAsync(HttpListenerContext ctx, string path,
                                              ServerState state, ServerActions actions)
    {
        string text;
        using (var reader = new StreamReader(ctx.Request.InputStream, Encoding.UTF8))
            text = await reader.ReadToEndAsync().ConfigureAwait(false);

        JsonElement root = default;
        try
        {
            using var doc = JsonDocument.Parse(string.IsNullOrWhiteSpace(text) ? "{}" : text);
            root = doc.RootElement.Clone();
        }
        catch { /* 非法 JSON → 空对象（对齐 Python） */ }

        switch (path)
        {
            case "/api/sweep":
            {
                var camp = root.Str("camp");
                if (string.IsNullOrEmpty(camp))
                {
                    await SendJsonAsync(ctx, 400, Err("缺少 camp")).ConfigureAwait(false);
                    return;
                }
                var t = state.NewTask("sweep", "绑定 " + camp);
                _ = Task.Run(() => actions.RunSweepAsync(camp, t));
                await SendJsonAsync(ctx, 200, TaskId(t.Id)).ConfigureAwait(false);
                return;
            }

            case "/api/download":
            {
                var camp = root.Str("camp");
                var items = new List<DownloadItem>();
                foreach (var e in root.Arr("items"))
                    items.Add(new DownloadItem { Title = e.Str("title"), When = e.Str("when") });
                if (string.IsNullOrEmpty(camp) || items.Count == 0)
                {
                    await SendJsonAsync(ctx, 400, Err("缺少 camp 或 items")).ConfigureAwait(false);
                    return;
                }
                var t = state.NewTask("download", $"下载 {camp}（{items.Count} 节）");
                _ = Task.Run(() => actions.RunDownloadAsync(camp, items, t));
                await SendJsonAsync(ctx, 200, TaskId(t.Id)).ConfigureAwait(false);
                return;
            }

            case "/api/settings":
            {
                var outDir = root.Str("out");
                if (!string.IsNullOrEmpty(outDir))
                {
                    state.SetOutRoot(outDir);
                    try { Directory.CreateDirectory(outDir); } catch { }
                }
                await SendJsonAsync(ctx, 200, new Dictionary<string, object>
                { ["out_root"] = state.CurrentOutRoot() }).ConfigureAwait(false);
                return;
            }

            case "/api/open_folder":
            {
                var p = root.Str("path");
                if (string.IsNullOrEmpty(p)) p = state.CurrentOutRoot();
                if (Directory.Exists(p))
                {
                    try
                    {
                        Process.Start(new ProcessStartInfo
                        { FileName = p, UseShellExecute = true });
                    }
                    catch { /* 打不开就忽略，仍返回 ok（对齐 os.startfile 的容错） */ }
                }
                await SendJsonAsync(ctx, 200, new Dictionary<string, object>
                { ["ok"] = true }).ConfigureAwait(false);
                return;
            }

            default:
                await SendJsonAsync(ctx, 404, Err("not found")).ConfigureAwait(false);
                return;
        }
    }

    // ── 静态资源 ──
    private static async Task SendUiAsync(HttpListenerContext ctx)
    {
        // ui.html 由 Xqd.Server.csproj 作为 Content 复制到输出目录，绝不改动根目录原件。
        var p = Path.Combine(AppContext.BaseDirectory, "ui.html");
        if (!File.Exists(p))
        {
            await SendJsonAsync(ctx, 500, Err("找不到 ui.html")).ConfigureAwait(false);
            return;
        }
        var data = await File.ReadAllBytesAsync(p).ConfigureAwait(false);
        await SendAsync(ctx, 200, data, "text/html; charset=utf-8").ConfigureAwait(false);
    }

    private static async Task ServeStaticAsync(HttpListenerContext ctx, string urlPath)
    {
        var rel = urlPath.TrimStart('/').Replace('/', Path.DirectorySeparatorChar);
        var baseDir = Path.GetFullPath(AppContext.BaseDirectory);
        if (!baseDir.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal))
            baseDir += Path.DirectorySeparatorChar;
        string full;
        try { full = Path.GetFullPath(Path.Combine(baseDir, rel)); }
        catch { await SendJsonAsync(ctx, 404, Err("not found")).ConfigureAwait(false); return; }
        // 防目录穿越：只允许 BaseDirectory 下的文件。
        if (!full.StartsWith(baseDir, StringComparison.OrdinalIgnoreCase) || !File.Exists(full))
        {
            await SendJsonAsync(ctx, 404, Err("not found")).ConfigureAwait(false);
            return;
        }
        var data = await File.ReadAllBytesAsync(full).ConfigureAwait(false);
        await SendAsync(ctx, 200, data, ContentTypeOf(full)).ConfigureAwait(false);
    }

    private static string ContentTypeOf(string path)
    {
        switch (Path.GetExtension(path).ToLowerInvariant())
        {
            case ".html": case ".htm": return "text/html; charset=utf-8";
            case ".css": return "text/css; charset=utf-8";
            case ".js": return "application/javascript; charset=utf-8";
            case ".json": return "application/json; charset=utf-8";
            case ".png": return "image/png";
            case ".jpg": case ".jpeg": return "image/jpeg";
            case ".gif": return "image/gif";
            case ".svg": return "image/svg+xml";
            case ".ico": return "image/x-icon";
            case ".woff": return "font/woff";
            case ".woff2": return "font/woff2";
            case ".txt": return "text/plain; charset=utf-8";
            case ".mp4": return "video/mp4";
            default: return "application/octet-stream";
        }
    }

    // ── 响应辅助 ──
    private static async Task SendJsonAsync<T>(HttpListenerContext ctx, int code, T obj)
    {
        var json = JsonSerializer.Serialize(obj, JsonOpts);
        await SendAsync(ctx, code, Encoding.UTF8.GetBytes(json),
                        "application/json; charset=utf-8").ConfigureAwait(false);
    }

    private static async Task SendAsync(HttpListenerContext ctx, int code, byte[] body, string ctype)
    {
        var resp = ctx.Response;
        resp.StatusCode = code;
        resp.ContentType = ctype;
        resp.ContentLength64 = body.LongLength;
        resp.AddHeader("Cache-Control", "no-store");
        await resp.OutputStream.WriteAsync(body, 0, body.Length).ConfigureAwait(false);
    }

    private static Dictionary<string, object> Err(string msg) =>
        new() { ["error"] = msg };

    private static Dictionary<string, object> TaskId(int id) =>
        new() { ["task"] = id };

    // ── 查询串（取第一个值，等价 parse_qs(...)[0]）──
    private static Dictionary<string, string> ParseQuery(string raw)
    {
        var d = new Dictionary<string, string>(StringComparer.Ordinal);
        if (string.IsNullOrEmpty(raw)) return d;
        var s = raw.StartsWith("?", StringComparison.Ordinal) ? raw.Substring(1) : raw;
        foreach (var part in s.Split('&'))
        {
            if (part.Length == 0) continue;
            int i = part.IndexOf('=');
            var k = WebUtility.UrlDecode(i < 0 ? part : part.Substring(0, i));
            var v = WebUtility.UrlDecode(i < 0 ? "" : part.Substring(i + 1));
            if (!d.ContainsKey(k)) d[k] = v;
        }
        return d;
    }

    private static string Q(Dictionary<string, string> d, string k) =>
        d.TryGetValue(k, out var v) ? v : null;
}
