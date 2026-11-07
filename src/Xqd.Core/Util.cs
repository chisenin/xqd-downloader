using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Xqd.Core;

/// <summary>JsonElement 取值助手：网关字段类型不固定（数字可能是字符串），统一容错。</summary>
public static class J
{
    public static JsonElement Parse(string text) => JsonDocument.Parse(text).RootElement.Clone();

    public static JsonElement Get(this JsonElement e, string key)
    {
        if (e.ValueKind == JsonValueKind.Object && e.TryGetProperty(key, out var v)) return v;
        return default;
    }

    public static string Str(this JsonElement e, string key, string def = "")
    {
        var v = e.Get(key);
        return StrSelf(v, def);
    }

    public static string StrSelf(this JsonElement v, string def = "")
    {
        if (v.ValueKind == JsonValueKind.String) return v.GetString() ?? def;
        if (v.ValueKind == JsonValueKind.Number) return v.GetRawText();
        if (v.ValueKind == JsonValueKind.True) return "true";
        if (v.ValueKind == JsonValueKind.False) return "false";
        return def;
    }

    public static long Long(this JsonElement e, string key, long def = 0)
    {
        var v = e.Get(key);
        if (v.ValueKind == JsonValueKind.Number && v.TryGetInt64(out var n)) return n;
        if (v.ValueKind == JsonValueKind.String && long.TryParse(v.GetString(), out var m)) return m;
        return def;
    }

    public static double Dbl(this JsonElement e, string key, double def = 0)
    {
        var v = e.Get(key);
        if (v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out var n)) return n;
        if (v.ValueKind == JsonValueKind.String &&
            double.TryParse(v.GetString(), NumberStyles.Any, CultureInfo.InvariantCulture, out var m))
            return m;
        return def;
    }

    public static bool Bool(this JsonElement e, string key, bool def = false)
    {
        var v = e.Get(key);
        if (v.ValueKind == JsonValueKind.True) return true;
        if (v.ValueKind == JsonValueKind.False) return false;
        return def;
    }

    public static List<JsonElement> Arr(this JsonElement e, string key)
    {
        var list = new List<JsonElement>();
        var v = e.Get(key);
        if (v.ValueKind == JsonValueKind.Array)
            foreach (var x in v.EnumerateArray()) list.Add(x);
        return list;
    }

    public static Dictionary<string, string> FlatStr(this JsonElement e)
    {
        var d = new Dictionary<string, string>();
        if (e.ValueKind != JsonValueKind.Object) return d;
        foreach (var p in e.EnumerateObject()) d[p.Name] = p.Value.StrSelf();
        return d;
    }
}

public static class Util
{
    /// <summary>
    /// 秒 → 天:时:分:秒（按需省略前导单位）。与 Python xqd_gui.fmt_dur 完全一致：
    /// 45 / 1:30 / 2:15:30 / 1:02:15:30；最高位不补零，其余两位。
    /// </summary>
    public static string FmtDur(double sec) => FmtClock(sec);

    /// <summary>倒计时：天:时:分:秒，省略前导零单位；最高位不补零，其余两位。</summary>
    public static string FmtClock(double sec)
    {
        if (sec < 0 || double.IsNaN(sec) || double.IsInfinity(sec)) return "--";
        var s = (long)Math.Round(sec);
        var d = s / 86400;
        var h = (s % 86400) / 3600;
        var m = (s % 3600) / 60;
        var ss = s % 60;
        if (d > 0) return $"{d}:{h:00}:{m:00}:{ss:00}";
        if (h > 0) return $"{h}:{m:00}:{ss:00}";
        if (m > 0) return $"{m}:{ss:00}";
        return ss.ToString(CultureInfo.InvariantCulture);
    }

    /// <summary>速率 → 紧凑字符串（与 Python fmt_speed 一致，不带空格）。</summary>
    public static string FmtSpeed(double bps)
    {
        if (bps <= 0 || double.IsNaN(bps)) return "--";
        if (bps < 1024) return $"{(long)bps}B/s";
        if (bps < 1024 * 1024) return $"{(long)(bps / 1024.0)}KB/s";
        return $"{bps / 1048576.0:0.0}MB/s";
    }

    public static string HumanSize(double bytes)
    {
        if (bytes <= 0) return "0";
        if (bytes < 1024 * 1024) return $"{bytes / 1024.0:0.0} KB";
        return $"{bytes / 1048576.0:0.0} MB";
    }

    public static string Md5Hex(string s)
    {
        using var md5 = MD5.Create();
        var bytes = md5.ComputeHash(Encoding.UTF8.GetBytes(s ?? ""));
        var sb = new StringBuilder();
        foreach (var b in bytes) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
        return sb.ToString();
    }

    public static string JoinUrl(string baseUrl, string rel)
    {
        if (string.IsNullOrEmpty(rel)) return baseUrl;
        if (rel.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ||
            rel.StartsWith("https://", StringComparison.OrdinalIgnoreCase)) return rel;
        var b = new Uri(baseUrl);
        return new Uri(b, rel).AbsoluteUri;
    }

    /// <summary>按 ? 拆分 URL 的路径与查询（保留三层目录）。</summary>
    public static (string path, string query) SplitQuery(string url)
    {
        var i = url.IndexOf('?');
        return i < 0 ? (url, "") : (url.Substring(0, i), url.Substring(i + 1));
    }

    public static string QueryWithout(string query, params string[] drop)
    {
        if (string.IsNullOrEmpty(query)) return "";
        var kept = new List<string>();
        foreach (var part in query.Split('&'))
        {
            if (string.IsNullOrEmpty(part)) continue;
            var name = part.Split('=')[0];
            var skip = false;
            foreach (var d in drop)
                if (string.Equals(name, d, StringComparison.OrdinalIgnoreCase)) { skip = true; break; }
            if (!skip) kept.Add(part);
        }
        return kept.Count > 0 ? "?" + string.Join("&", kept) : "";
    }
}
