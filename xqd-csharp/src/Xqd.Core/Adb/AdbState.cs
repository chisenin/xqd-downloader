using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Xqd.Core;

namespace Xqd.Core.Adb;

/// <summary>names.json 的一条：fileId → {name, when, camp}（对应 xqd_app.py names.json）。</summary>
internal sealed class NameEntry
{
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("when")] public string When { get; set; } = "";
    [JsonPropertyName("camp")] public string Camp { get; set; } = "";
}

/// <summary>links.json 的一条：fileId → {url, ts, camp}（对应 xqd_app.py links.json）。</summary>
internal sealed class LinkEntry
{
    [JsonPropertyName("url")] public string Url { get; set; } = "";
    [JsonPropertyName("ts")] public double Ts { get; set; }
    [JsonPropertyName("camp")] public string Camp { get; set; } = "";
}

/// <summary>catalog.json 的一条：camp → [{title, when, index}]。</summary>
internal sealed class CatalogEntry
{
    [JsonPropertyName("title")] public string Title { get; set; } = "";
    [JsonPropertyName("when")] public string When { get; set; } = "";
    [JsonPropertyName("index")] public int Index { get; set; }
}

/// <summary>
/// 旧路径持久化状态：names / links / catalog 三个 JSON。
/// 对应 xqd.py 的 load_json/save_json 与 xqd_app.py 的 NAMES_FILE / LINKS_FILE / CATALOG_FILE。
/// 落盘目录取 Config.ToolDir（每用户持久目录，等价于 Python 的 HERE/state）。
/// JSON 字段名用 [JsonPropertyName] 保持与 Python 一致（name/when/camp/url/ts/title/index），
/// 便于必要时与既有 state 文件互通。
/// </summary>
internal sealed class AdbState
{
    private static readonly JsonSerializerOptions JsonOpt = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
    };

    private readonly string _dir;
    private readonly string _namesPath;
    private readonly string _linksPath;
    private readonly string _catalogPath;

    public Dictionary<string, NameEntry> Names { get; private set; } = new();
    public Dictionary<string, LinkEntry> Links { get; private set; } = new();
    public Dictionary<string, List<CatalogEntry>> Catalogs { get; private set; } = new();

    public AdbState(string dir = null)
    {
        _dir = string.IsNullOrEmpty(dir) ? Path.Combine(Config.ToolDir, "adb_state") : dir;
        _namesPath = Path.Combine(_dir, "names.json");
        _linksPath = Path.Combine(_dir, "links.json");
        _catalogPath = Path.Combine(_dir, "catalog.json");
        Load();
    }

    private void Load()
    {
        Names = Read<Dictionary<string, NameEntry>>(_namesPath) ?? new Dictionary<string, NameEntry>();
        Links = Read<Dictionary<string, LinkEntry>>(_linksPath) ?? new Dictionary<string, LinkEntry>();
        Catalogs = Read<Dictionary<string, List<CatalogEntry>>>(_catalogPath)
                   ?? new Dictionary<string, List<CatalogEntry>>();
    }

    /// <summary>对应 xqd.load_json：文件不存在 / 解析失败都返回默认值。</summary>
    private static T Read<T>(string path) where T : class
    {
        try
        {
            if (!File.Exists(path)) return null;
            return JsonSerializer.Deserialize<T>(File.ReadAllText(path, Encoding.UTF8), JsonOpt);
        }
        catch { return null; }
    }

    private static void Write<T>(string path, T obj)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path) ?? ".");
            File.WriteAllText(path, JsonSerializer.Serialize(obj, JsonOpt), new UTF8Encoding(false));
        }
        catch (Exception e) { Console.Error.WriteLine("保存 ADB 状态失败：" + e.Message); }
    }

    public void Save()
    {
        Write(_namesPath, Names);
        Write(_linksPath, Links);
        Write(_catalogPath, Catalogs);
    }

    // ── sweep 写入 ────────────────────────────────────────────────

    /// <summary>绑定课名：fileId 已在 names 里则不覆盖（与 sweep_camp 一致）。</summary>
    public bool PutName(string fileId, string name, string when, string camp)
    {
        if (string.IsNullOrEmpty(fileId) || Names.ContainsKey(fileId)) return false;
        Names[fileId] = new NameEntry { Name = name, When = when, Camp = camp };
        return true;
    }

    /// <summary>记录清单 → 链接（对应 sweep_camp 里 links[fids[0]] = {...}）。</summary>
    public void PutLink(string fileId, string url, string camp)
    {
        if (string.IsNullOrEmpty(fileId) || string.IsNullOrEmpty(url)) return;
        Links[fileId] = new LinkEntry
        {
            Url = url,
            Ts = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
            Camp = camp,
        };
    }

    public void PutCatalog(string camp, List<CatalogEntry> items) => Catalogs[camp] = items;

    // ── 反查：课 → fileId → URL ────────────────────────────────────

    /// <summary>
    /// 由 (营名, 课名, 日期) 反查 fileId。
    /// ★ 一个清单可能含多个业务 fileId，names 里全都绑了课名，但 URL 只存在 links[fids[0]]。
    ///   因此优先返回「同时是 links 键」的那个 fileId。
    /// </summary>
    public string FindFileId(string camp, string title, string when)
    {
        string fallback = "";
        foreach (var kv in Names)
        {
            var e = kv.Value;
            if (e.Camp != (camp ?? "") || e.Name != (title ?? "")) continue;
            if (!string.IsNullOrEmpty(when) && e.When != when) continue;
            if (Links.ContainsKey(kv.Key)) return kv.Key;   // 有 URL 的优先
            if (fallback.Length == 0) fallback = kv.Key;
        }
        return fallback;
    }

    /// <summary>
    /// 由 lesson 找可直连的清单 URL：
    ///   1) lesson.FileId 直接命中 links；
    ///   2) 否则遍历 links 键，看其 names 条目的 (camp,title,when) 是否匹配。
    /// </summary>
    public string FindUrl(string camp, Lesson lesson)
    {
        if (lesson == null) return null;
        var fid = lesson.FileId ?? "";
        if (fid.Length > 0 && Links.TryGetValue(fid, out var direct) &&
            !string.IsNullOrEmpty(direct.Url))
            return direct.Url;

        foreach (var kv in Links)
        {
            if (string.IsNullOrEmpty(kv.Value.Url)) continue;
            if (!Names.TryGetValue(kv.Key, out var ne)) continue;
            if (ne.Camp != (camp ?? "") || ne.Name != (lesson.Title ?? "")) continue;
            if (!string.IsNullOrEmpty(lesson.When) && ne.When != lesson.When) continue;
            return kv.Value.Url;
        }
        return null;
    }
}
