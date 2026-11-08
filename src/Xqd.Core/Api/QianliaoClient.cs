using System.Text.Json;
using Xqd.Core;

namespace Xqd.Core.Api;

/// <summary>
/// 兴趣岛业务网关底层客户端 —— 对应 Python 的 _lel/api/qianliao.py（QldClient）。
///
/// 已验证契约（docs/01-已验证事实.md 〇之一 / docs/09-兴趣岛业务API.md）：
///   POST https://m.qianliao.net/financial/api/transfer/gate/&lt;endpoint&gt;
///   Body: {"transferData": {...}}
///   成功码在 state.code（不是顶层 code！）
///   网关出错返回 HTML（title=授权登录），先判首字节再解析 JSON。
///   必须禁用系统代理，否则请求被代理吞掉返回 HTML —— 统一复用 Net（UseProxy=false）。
/// </summary>
public sealed class QianliaoClient
{
    public const string DefaultHost = "m.qianliao.net";

    // getCoursePlayUrl 返回里可能承载播放地址的键（按优先级）。
    private static readonly string[] UrlKeys = { "playUrl", "coursePlayUrl", "url" };
    private const int MaxDepth = 8;

    public string Host { get; }
    public string Cookie { get; set; }

    public string GatewayUrl => "https://" + Host + "/financial/api/transfer";

    public QianliaoClient(string cookie = null, string host = DefaultHost)
    {
        Host = string.IsNullOrEmpty(host) ? DefaultHost : host;
        // 凭据单一入口：没显式给就从 XQD_COOKIE / QLD_COOKIE / cookie.txt 读。
        Cookie = string.IsNullOrEmpty(cookie) ? Creds.LoadCookie() : cookie;
    }

    /// <summary>
    /// 调业务网关，返回 data 节点（JsonElement）。失败抛 InvalidOperationException。
    /// 与 QldClient.api 一致：HTTP 层异常重试，code=110（未登录）不重试。
    /// </summary>
    public async Task<JsonElement> ApiAsync(string endpoint,
        Dictionary<string, object> transferData = null,
        int timeoutSeconds = 30, int retry = 2, CancellationToken ct = default)
    {
        var td = transferData ?? new Dictionary<string, object>();
        var body = JsonSerializer.Serialize(new Dictionary<string, Dictionary<string, object>>
        {
            ["transferData"] = td,
        });
        var url = GatewayUrl + endpoint;
        // Content-Type 由 Net.PostJsonAsync 设为 application/json;charset=UTF-8；
        // User-Agent / Accept 由 Net 的静态 Client 统一带 okhttp/4.9.0。
        var headers = new List<KeyValuePair<string, string>>
        {
            new("Cookie", Cookie ?? ""),
            new("Origin", "https://" + Host),
            new("Referer", "https://" + Host + "/"),
        };

        string last = "";
        for (int attempt = 0; attempt <= retry; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            string raw;
            try
            {
                raw = await Net.PostJsonAsync(url, body, headers, timeoutSeconds, ct)
                               .ConfigureAwait(false);
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception e)
            {
                last = "请求失败：" + e.Message;
                if (attempt < retry) { await Task.Delay(800, ct).ConfigureAwait(false); continue; }
                break;
            }

            // m.qianliao.net 出错时返回 HTML（title=授权登录）而非 JSON，
            // 200 不等于成功 —— 先判首字节是 '{' 还是 '<' 再解析。
            var head = (raw ?? "").TrimStart();
            if (head.Length == 0 || head[0] != '{')
            {
                last = "网关返回非 JSON（可能未授权或被系统代理拦截；首字节 '"
                     + (head.Length > 0 ? head[0].ToString() : "") + "'）";
                if (attempt < retry) { await Task.Delay(800, ct).ConfigureAwait(false); continue; }
                break;
            }

            JsonElement root;
            try { root = J.Parse(raw); }
            catch (Exception e)
            {
                last = "JSON 解析失败：" + e.Message;
                if (attempt < retry) { await Task.Delay(800, ct).ConfigureAwait(false); continue; }
                break;
            }

            var state = root.Get("state");
            long code = state.Long("code", -999);   // 缺失 state/code 视为失败
            if (code == 0)
            {
                var data = root.Get("data");
                return data.ValueKind == JsonValueKind.Object || data.ValueKind == JsonValueKind.Array
                    ? data : J.Parse("{}");
            }

            last = "code=" + code + " msg=" + state.Str("msg");
            if (code == 110) break;   // 未登录，重试无用
            if (attempt < retry) await Task.Delay(800, ct).ConfigureAwait(false);
        }
        throw new InvalidOperationException(endpoint + " 失败：" + last);
    }

    // ── 业务端点（对照 QldClient 的 my_courses_v2 / playlist / play_url）──

    public Task<JsonElement> MyCourseListV2Async(Dictionary<string, object> transferData = null,
        CancellationToken ct = default) =>
        ApiAsync("/gate/course/myCourseListV2", transferData, ct: ct);

    public Task<JsonElement> PlayListOfCourseAsync(string campId,
        CancellationToken ct = default) =>
        ApiAsync("/gate/course/playListOfCourse", new Dictionary<string, object>
        {
            ["campId"] = campId ?? "",
            ["onlyCourseCatalogue"] = true,
        }, ct: ct);

    public Task<JsonElement> GetCoursePlayUrlAsync(string businessId, string businessType,
        string topicId, string roomId, string videoHost = "",
        CancellationToken ct = default) =>
        ApiAsync("/gate/course/getCoursePlayUrl", new Dictionary<string, object>
        {
            ["videoHost"] = videoHost ?? "",
            ["roomId"] = roomId ?? "",
            ["topicId"] = topicId ?? "",
            ["businessId"] = businessId ?? "",
            ["businessType"] = string.IsNullOrEmpty(businessType) ? "camp" : businessType,
        }, ct: ct);

    /// <summary>
    /// getCoursePlayUrl 的 data 可能多层嵌套（playUrl / coursePlayUrl / url，
    /// 值还可能是对象或数组），逐层找第一个 http 开头的字符串。
    /// 先按 playUrl → coursePlayUrl → url 的键顺序，再递归其余键兜底。
    /// </summary>
    public static string FindPlayUrl(JsonElement data) => FindHttp(data, 0);

    private static string FindHttp(JsonElement node, int depth)
    {
        if (depth > MaxDepth) return "";
        switch (node.ValueKind)
        {
            case JsonValueKind.String:
            {
                var s = node.GetString();
                return s != null && s.StartsWith("http", StringComparison.OrdinalIgnoreCase)
                    ? s : "";
            }
            case JsonValueKind.Array:
                foreach (var item in node.EnumerateArray())
                {
                    var r = FindHttp(item, depth + 1);
                    if (!string.IsNullOrEmpty(r)) return r;
                }
                return "";
            case JsonValueKind.Object:
                // 1) 优先键（按 playUrl / coursePlayUrl / url 顺序）
                foreach (var key in UrlKeys)
                {
                    var r = FindHttp(node.Get(key), depth + 1);
                    if (!string.IsNullOrEmpty(r)) return r;
                }
                // 2) 其余键兜底（响应再套一层对象时仍能找到）
                foreach (var p in node.EnumerateObject())
                {
                    if (IsUrlKey(p.Name)) continue;
                    var r = FindHttp(p.Value, depth + 1);
                    if (!string.IsNullOrEmpty(r)) return r;
                }
                return "";
            default:
                return "";
        }
    }

    private static bool IsUrlKey(string name)
    {
        foreach (var k in UrlKeys)
            if (string.Equals(name, k, StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }
}
