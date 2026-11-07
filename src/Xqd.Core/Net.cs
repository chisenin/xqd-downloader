using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core;

/// <summary>
/// 网络层 —— **必须禁用系统代理**，否则业务网关/CDN 请求会被代理吞掉返回 HTML。
/// 对应 Python 的 urllib.request.ProxyHandler({})。
/// TLS 校验证书关闭（与 Python ssl.CERT_NONE 一致）。
/// </summary>
public static class Net
{
    public const string UA = "okhttp/4.9.0";

    private static readonly HttpClient Client = CreateClient();

    public static HttpClient CreateClient(int timeoutSeconds = 60)
    {
        var handler = new HttpClientHandler
        {
            UseProxy = false,
            Proxy = null,
            AllowAutoRedirect = true,
            ServerCertificateCustomValidationCallback =
                HttpClientHandler.DangerousAcceptAnyServerCertificateValidator,
        };
        var c = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(timeoutSeconds) };
        c.DefaultRequestHeaders.TryAddWithoutValidation("User-Agent", UA);
        c.DefaultRequestHeaders.TryAddWithoutValidation("Accept", "application/json, text/plain, */*");
        return c;
    }

    private static HttpRequestMessage Req(HttpMethod method, string url,
                                          IEnumerable<KeyValuePair<string, string>> headers = null)
    {
        var req = new HttpRequestMessage(method, url);
        if (headers != null)
            foreach (var kv in headers)
                req.Headers.TryAddWithoutValidation(kv.Key, kv.Value);
        return req;
    }

    public static async Task<byte[]> GetBytesAsync(string url, int timeoutSeconds = 30,
                                                    IEnumerable<KeyValuePair<string, string>> headers = null,
                                                    CancellationToken ct = default)
    {
        using var req = Req(HttpMethod.Get, url, headers);
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
        using var resp = await Client.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, cts.Token)
                                     .ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadAsByteArrayAsync(cts.Token).ConfigureAwait(false);
    }

    public static async Task<string> GetTextAsync(string url, int timeoutSeconds = 30,
                                                   IEnumerable<KeyValuePair<string, string>> headers = null,
                                                   CancellationToken ct = default)
    {
        var bytes = await GetBytesAsync(url, timeoutSeconds, headers, ct).ConfigureAwait(false);
        return Encoding.UTF8.GetString(bytes);
    }

    public static async Task<Stream> OpenStreamAsync(string url, int timeoutSeconds = 60,
                                                      IEnumerable<KeyValuePair<string, string>> headers = null,
                                                      CancellationToken ct = default)
    {
        using var req = Req(HttpMethod.Get, url, headers);
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
        var resp = await Client.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, cts.Token)
                               .ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadAsStreamAsync(cts.Token).ConfigureAwait(false);
    }

    /// <summary>POST JSON，返回原始响应文本（网关出错时返回 HTML，由调用方判首字节）。</summary>
    public static async Task<string> PostJsonAsync(string url, string json,
                                                    IEnumerable<KeyValuePair<string, string>> headers = null,
                                                    int timeoutSeconds = 30,
                                                    CancellationToken ct = default)
    {
        using var req = new HttpRequestMessage(HttpMethod.Post, url)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json")
        };
        req.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json") { CharSet = "UTF-8" };
        if (headers != null)
            foreach (var kv in headers)
                req.Headers.TryAddWithoutValidation(kv.Key, kv.Value);
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
        using var resp = await Client.SendAsync(req, cts.Token).ConfigureAwait(false);
        return await resp.Content.ReadAsStringAsync(cts.Token).ConfigureAwait(false);
    }

    /// <summary>取 Content-Length（不下载正文），用于总字节估算。</summary>
    public static async Task<long> HeadLengthAsync(string url, int timeoutSeconds = 30,
                                                    CancellationToken ct = default)
    {
        using var req = new HttpRequestMessage(HttpMethod.Head, url);
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
        using var resp = await Client.SendAsync(req, cts.Token).ConfigureAwait(false);
        return resp.Content.Headers.ContentLength ?? 0;
    }
}
