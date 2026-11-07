using Xqd.Core;

namespace Xqd.Core.Api;

/// <summary>
/// xqd_api.py 的语义兼容静态入口 —— 供 web 服务 / CLI 使用。
/// 返回 Python 风格松散字典（键名与 xqd_api.py 一致，便于直接序列化成原 JSON），
/// 核心业务复用 QianliaoPlatform（强类型 IPlatform 实现），此处只做形态转换与编排。
/// 命名走 Naming.CourseFilenameApi（-1/-2 重名兼容规则）。
/// </summary>
public static class ApiCompat
{
    // 对应 xqd_api.py 的 _CLIENT 单例：QldClient 构造时自动 load_cookie。
    private static QianliaoPlatform _platform;
    private static QianliaoPlatform P => _platform ??= new QianliaoPlatform();

    // ── 营列表 ──
    /// <summary>list_camps(tab) → [{name, badge, type, count}]，tab ∈ 全部/正式营/体验营/轻课。</summary>
    public static List<Dictionary<string, object>> ListCamps(string tab = "全部")
    {
        var camps = P.ListCampsAsync(tab ?? "全部").GetAwaiter().GetResult();
        var result = new List<Dictionary<string, object>>();
        var seen = new HashSet<string>();
        foreach (var c in camps)
        {
            // 「全部」按 id 去重（同一营可能跨标签重复出现）。
            var id = c.CampId;
            if (!string.IsNullOrEmpty(id) && !seen.Add(id)) continue;
            var type = QianliaoPlatform.CampTypeOf(c.SkuType);
            result.Add(new Dictionary<string, object>
            {
                ["name"] = c.Name,
                ["badge"] = c.Count > 0 ? type + "•共" + c.Count + "课" : type,
                ["type"] = type,
                ["count"] = c.Count,
            });
        }
        return result;
    }

    // ── camp_info ──
    /// <summary>camp_info(name) → {campId, periodId, skuType, businessType, businessId, campName}。</summary>
    public static Dictionary<string, object> CampInfo(string name)
    {
        var camp = P.LookupCamp(name);
        if (camp == null) return new Dictionary<string, object>();
        return new Dictionary<string, object>
        {
            ["campId"] = camp.CampId,
            ["periodId"] = camp.PeriodId,
            ["skuType"] = camp.SkuType,
            ["businessType"] = camp.BusinessType,
            ["businessId"] = camp.BusinessId,
            ["campName"] = camp.Name,
        };
    }

    // ── 课表 ──
    /// <summary>camp_catalog(camp) → [{title, when, date, index, topicId, roomId, type, duration, fileId, isReplay}]。</summary>
    public static List<Dictionary<string, object>> CampCatalog(string camp)
    {
        var campObj = P.LookupCamp(camp) ?? new Camp { Name = camp };
        var lessons = P.CampCatalogAsync(campObj).GetAwaiter().GetResult();
        var result = new List<Dictionary<string, object>>();
        foreach (var l in lessons)
        {
            result.Add(new Dictionary<string, object>
            {
                ["title"] = l.Title,
                ["when"] = l.When,
                ["date"] = l.WhenDate,
                ["index"] = l.Index,
                ["topicId"] = l.TopicId,
                ["roomId"] = l.RoomId,
                ["type"] = l.Type,
                ["duration"] = l.Duration,
                ["fileId"] = l.FileId,
                ["isReplay"] = null,     // 课表未单独保留该字段，键位保留以兼容旧消费者
            });
        }
        return result;
    }

    // ── 播放地址 ──
    /// <summary>resolve(camp, item) → 可直连 m3u8 URL；失败返回 ""（对应 Python 的 None）。</summary>
    public static string Resolve(string camp, Dictionary<string, object> item)
    {
        try
        {
            var campObj = P.LookupCamp(camp) ?? new Camp { Name = camp };
            return P.ResolveAsync(campObj, ItemToLesson(item, camp, campObj))
                     .GetAwaiter().GetResult();
        }
        catch { return ""; }
    }

    /// <summary>resolve_all(camp, items, progress) → {index: {url, totalSeconds}}。</summary>
    public static Dictionary<int, Dictionary<string, object>> ResolveAll(
        string camp, IEnumerable<Dictionary<string, object>> items,
        Action<int, int, string> progress = null)
    {
        var list = items as IList<Dictionary<string, object>> ?? items.ToList();
        var result = new Dictionary<int, Dictionary<string, object>>();
        for (int i = 0; i < list.Count; i++)
        {
            var it = list[i];
            var url = Resolve(camp, it);
            if (!string.IsNullOrEmpty(url))
            {
                result[GetInt(it, "index")] = new Dictionary<string, object>
                {
                    ["url"] = url,
                    ["totalSeconds"] = GetDbl(it, "duration"),
                };
            }
            progress?.Invoke(i + 1, list.Count, GetStr(it, "title"));
        }
        return result;
    }

    // ── 文件命名 ──
    /// <summary>
    /// course_filename(item, seq, used) —— 兼容版命名（营内已用名去重追加 -1/-2）。
    /// 委托 Naming.CourseFilenameApi，与 xqd_api.py 旧签名一致。
    /// </summary>
    public static string CourseFilename(Dictionary<string, object> item,
        int? seq = null, HashSet<string> used = null)
    {
        int n = seq ?? (GetInt(item, "index") + 1);
        return Naming.CourseFilenameApi(GetStr(item, "title"), n, GetStr(item, "date"), used);
    }

    // ── 统一下载入口 ──
    /// <summary>
    /// download_items(camp, items, ...) → (ok, fail, skip)。
    /// 对齐 xqd_api.py：建营目录、>100000B 已存在跳过、课表按标题配对、逐节驱动引擎。
    /// 实际「解析→下载→封装→校验」交给 Services.Engine（DownloadRequest 不含 url，
    /// 引擎按 IDataSource.ResolveAsync 现场解析，签名天然新鲜）。
    /// </summary>
    public static (int Ok, int Fail, int Skip) DownloadItems(
        string camp,
        IEnumerable<Dictionary<string, object>> items,
        Action<string> taskLog = null,
        Action<double, int, string> progress = null,
        string outRoot = null)
    {
        outRoot = string.IsNullOrEmpty(outRoot)
            ? Config.EffectiveOutDir(Config.Load()) : outRoot;
        var list = items as IList<Dictionary<string, object>> ?? items.ToList();
        var campObj = P.LookupCamp(camp) ?? new Camp { Name = camp };

        var catalog = CampCatalog(camp);
        var byTitle = new Dictionary<string, Dictionary<string, object>>();
        foreach (var c in catalog)
        {
            var t = GetStr(c, "title");
            if (!byTitle.ContainsKey(t)) byTitle[t] = c;   // setdefault：同名取第一节
        }

        var folder = Path.Combine(outRoot, Naming.CampFolder(camp));
        Directory.CreateDirectory(folder);

        var used = new HashSet<string>();
        int ok = 0, fail = 0, skip = 0;
        int total = list.Count;
        for (int i = 0; i < total; i++)
        {
            var it = list[i];
            var title = GetStr(it, "title");
            var meta = byTitle.TryGetValue(title, out var m) ? m : null;
            var outPath = Path.Combine(folder, CourseFilename(meta ?? it, used: used));

            if (File.Exists(outPath) && new FileInfo(outPath).Length > 100000)
            {
                taskLog?.Invoke("已存在，跳过：" + title);
                skip++;
                continue;
            }
            if (meta == null)
            {
                taskLog?.Invoke("课表里找不到：" + title);
                fail++;
                continue;
            }

            var req = new DownloadRequest
            {
                Camp = campObj,
                Lesson = ItemToLesson(meta, camp, campObj),
                OutPath = outPath,
                Quality = "max",
            };
            var cb = new DownloadCallbacks
            {
                Log = taskLog,
                Progress = p => progress?.Invoke(i + p.Percent / 100.0, total, title),
            };

            DownloadResult result;
            try
            {
                result = Services.Engine.DownloadAsync(req, cb).GetAwaiter().GetResult();
            }
            catch (Exception e)
            {
                taskLog?.Invoke("✗ " + title + "  " + e.Message);
                fail++;
                continue;
            }

            if (result != null && result.Ok)
            {
                ok++;
                double size = File.Exists(outPath)
                    ? new FileInfo(outPath).Length / 1048576.0 : 0;
                taskLog?.Invoke($"✓ {title}  [{size:0.0}MB] {result.Message}");
            }
            else
            {
                fail++;
                taskLog?.Invoke("✗ " + title + "  " + (result?.Message ?? "下载失败"));
            }
        }
        return (ok, fail, skip);
    }

    // ── 内部：xqd_api 风格的 item(dict) ↔ Lesson ──
    private static Lesson ItemToLesson(Dictionary<string, object> it, string camp, Camp campObj)
    {
        return new Lesson
        {
            Index = GetInt(it, "index"),
            Title = GetStr(it, "title"),
            When = GetStr(it, "when"),
            WhenDate = GetStr(it, "date"),
            Duration = GetDbl(it, "duration"),
            Type = GetStr(it, "type"),
            TopicId = GetStr(it, "topicId"),
            RoomId = GetStr(it, "roomId"),
            FileId = GetStr(it, "fileId"),
            CampName = camp,
            CampOfRow = campObj,
        };
    }

    private static string GetStr(Dictionary<string, object> d, string key) =>
        d != null && d.TryGetValue(key, out var v) && v != null ? v.ToString() : "";

    private static int GetInt(Dictionary<string, object> d, string key)
    {
        if (d == null || !d.TryGetValue(key, out var v) || v == null) return 0;
        try { return Convert.ToInt32(v); } catch { return 0; }
    }

    private static double GetDbl(Dictionary<string, object> d, string key)
    {
        if (d == null || !d.TryGetValue(key, out var v) || v == null) return 0;
        try { return Convert.ToDouble(v); } catch { return 0; }
    }
}
