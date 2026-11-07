using System.Text.Json;
using Xqd.Core;

namespace Xqd.Core.Api;

/// <summary>
/// 兴趣岛平台适配器 —— 对应 Python 的 xqd_platform.py（QianliaoPlatform / Platform / REGISTRY），
/// 同时吸收 xqd_api.py 的 camp_info 缓存与反查语义。
///
/// C# 侧「REGISTRY / create_platform」的职责由公共契约 Services.CreatePlatform 承担
/// （它固定 new 本类），因此这里只保留实现本身，不再另起注册表。
/// </summary>
public sealed class QianliaoPlatform : IPlatform
{
    public const string PlatformKey = "qianliao";

    private static readonly IReadOnlyList<string> Kinds = new[] { "正式营", "体验营" };

    // skyType 参数把营分类隔开（已验证事实 〇之一）：
    //   FINANCIAL → 正式营 9 个 / INTENTION → 体验营 1 个 / 不传 → 全部（含公开课）。
    private static readonly Dictionary<string, string> SkyTypes = new()
    {
        ["正式营"] = "FINANCIAL",
        ["体验营"] = "INTENTION",
    };

    private readonly QianliaoClient _client;
    // camp_info 的等价物：营名 → Camp（含 campId/periodId/skuType/businessType/businessId）。
    private readonly Dictionary<string, Camp> _campIndex = new();
    private readonly Dictionary<string, List<Lesson>> _catalogs = new();

    public QianliaoPlatform(string cookie = "")
    {
        _client = new QianliaoClient(cookie);
    }

    /// <summary>需要就地刷新授权时可用（Cookie 兜底读取在 QianliaoClient 构造里完成）。</summary>
    public QianliaoClient Client => _client;

    // ── IPlatform ──
    public string PlatformId => PlatformKey;
    public string DisplayName => "兴趣岛";
    public IReadOnlyList<string> CampKinds => Kinds;
    public DataSourceMode Mode => DataSourceMode.Api;

    // ── 营列表 ──
    public async Task<List<Camp>> ListCampsAsync(string kind, CancellationToken ct = default)
    {
        kind = kind ?? "";
        // 轻课在 App 内已确认为空 → 直接返回空列表，绝不探测。
        if (kind == "轻课") return new List<Camp>();

        string sky = SkyTypes.TryGetValue(kind, out var s) ? s : null;   // 全部/其它 → 不传
        var td = new Dictionary<string, object>
        {
            ["page"] = new Dictionary<string, object> { ["page"] = 1, ["size"] = 200 },
        };
        if (sky != null) td["skyType"] = sky;

        var data = await _client.MyCourseListV2Async(td, ct).ConfigureAwait(false);
        var camps = new List<Camp>();
        foreach (var c in data.Arr("courses"))
        {
            var camp = ParseCamp(c, kind);
            camps.Add(camp);
            // 累积式缓存（不清空），便于 camp_info 反查；多次拉不同 tab 会自然合并。
            if (!string.IsNullOrEmpty(camp.Name)) _campIndex[camp.Name] = camp;
        }
        return camps;
    }

    private static Camp ParseCamp(JsonElement c, string kind)
    {
        var sku = c.Str("skuType");
        var total = c.Long("courseTotalNum");
        return new Camp
        {
            Name = c.Str("campName"),
            CampId = c.Str("campId"),        // 数字耐容错；公开课为 null → ""
            Kind = string.IsNullOrEmpty(kind) ? CampTypeOf(sku) : kind,
            Count = (int)total,
            Badge = total + "节",
            PeriodId = c.Str("periodId"),
            SkuType = sku,
            BusinessType = c.Str("businessType"),
            BusinessId = c.Str("businessId"),
        };
    }

    /// <summary>skuType → 中文营类型（与 xqd_api.list_camps 判定一致）。</summary>
    public static string CampTypeOf(string sku) =>
        sku == "FINANCIAL" ? "正式营" :
        (sku == "LAUNCH" || sku == "INTENTION") ? "体验营" : "公开课";

    /// <summary>camp_info 反查：缓存命中直接给；未命中逐个标签重拉直到找到。</summary>
    private async Task<Camp> EnsureCampAsync(string name, CancellationToken ct)
    {
        if (string.IsNullOrEmpty(name)) return null;
        if (_campIndex.TryGetValue(name, out var hit)) return hit;
        foreach (var kind in new[] { "正式营", "体验营", "全部" })
        {
            await ListCampsAsync(kind, ct).ConfigureAwait(false);
            if (_campIndex.TryGetValue(name, out hit)) return hit;
        }
        return null;
    }

    /// <summary>供 xqd_api.camp_info 语义的同步兼容入口使用。</summary>
    public Camp LookupCamp(string name) =>
        EnsureCampAsync(name, default).GetAwaiter().GetResult();

    // ── 课表 ──
    public async Task<List<Lesson>> CampCatalogAsync(Camp camp, CancellationToken ct = default)
    {
        var name = camp?.Name ?? "";
        if (_catalogs.TryGetValue(name, out var cached)) return cached;

        var info = camp;
        if (string.IsNullOrEmpty(info?.CampId))
            info = await EnsureCampAsync(name, ct).ConfigureAwait(false);

        var campId = info?.CampId ?? "";
        // 公开课没有 campId，playListOfCourse 拿不到 → 空列表（对齐 xqd_api.camp_catalog）。
        if (string.IsNullOrEmpty(campId)) return new List<Lesson>();

        var data = await _client.PlayListOfCourseAsync(campId, ct).ConfigureAwait(false);
        var lessons = new List<Lesson>();
        int index = 0;
        foreach (var c in data.Arr("courses"))
        {
            long start = c.Long("startTime");
            lessons.Add(new Lesson
            {
                // 课表数组顺序 == App 列表顺序 == 成品序号；Index 从 0 起。
                Index = index++,
                Title = c.Str("name"),
                When = Naming.FmtWhen(start),        // MM.DD HH:MM
                WhenDate = Naming.FmtDate(start),    // YYYY.MM.DD
                Duration = c.Dbl("duration"),
                Type = c.Str("type"),
                TopicId = c.Str("topicId"),
                RoomId = c.Str("roomId"),
                FileId = c.Str("playUrl"),           // 保留 playUrl
                CampName = name,
                CampOfRow = info,                    // 逐行绑定所属营，不按合并行号重排
            });
        }
        _catalogs[name] = lessons;
        return lessons;
    }

    // ── 播放地址 ──
    public async Task<string> ResolveAsync(Camp camp, Lesson lesson, CancellationToken ct = default)
    {
        var name = camp?.Name ?? lesson?.CampName ?? "";
        var info = camp;
        if (string.IsNullOrEmpty(info?.CampId))
            info = await EnsureCampAsync(name, ct).ConfigureAwait(false);

        var campId = info?.CampId ?? "";
        string businessType, businessId;
        if (string.IsNullOrEmpty(campId))
        {
            // 公开课无 campId → OPEN_COURSE + periodId。
            businessType = "OPEN_COURSE";
            businessId = info?.PeriodId ?? "";
        }
        else
        {
            businessType = string.Equals(lesson?.Type, "OPEN_COURSE",
                StringComparison.OrdinalIgnoreCase) ? "OPEN_COURSE" : "camp";
            businessId = campId;
        }

        var topicId = lesson?.TopicId ?? "";
        var roomId = lesson?.RoomId ?? "";
        if (string.IsNullOrEmpty(topicId) && string.IsNullOrEmpty(roomId))
            throw new InvalidOperationException("缺少 topicId / roomId，无法解析播放地址");

        var data = await _client.GetCoursePlayUrlAsync(businessId, businessType,
            topicId, roomId, "", ct).ConfigureAwait(false);
        var url = QianliaoClient.FindPlayUrl(data);
        if (string.IsNullOrEmpty(url))
            throw new InvalidOperationException(
                "未取得播放地址：getCoursePlayUrl 响应里找不到 http 播放地址");
        return url;
    }

    // ── 授权 ──
    public async Task<(bool Ok, string Message)> CheckAuthAsync(CancellationToken ct = default)
    {
        if (string.IsNullOrEmpty(_client.Cookie)) return (false, "尚未获取授权");
        try
        {
            await _client.ApiAsync("/gate/course/myCourseListV2", new Dictionary<string, object>
            {
                ["skyType"] = "FINANCIAL",
                ["page"] = new Dictionary<string, object> { ["page"] = 1, ["size"] = 1 },
            }, timeoutSeconds: 20, retry: 0, ct: ct).ConfigureAwait(false);
            return (true, "授权有效");
        }
        catch (Exception e)
        {
            return (false, "授权无效：" + e.Message);
        }
    }
}
