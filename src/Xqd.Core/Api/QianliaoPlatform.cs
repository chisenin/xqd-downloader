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

    private static readonly IReadOnlyList<string> Kinds = new[] { "全部", "正式营", "体验营", "公开课" };

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

    /// <summary>
    /// ★ v1.6.1：缓存字典的锁。
    ///   这两个字典会被**两个线程**同时访问：
    ///   · UI 线程 —— CatalogWorkerAsync 读/写 _catalogs
    ///   · 下载线程 —— ResolveAsync → EnsureCampAsync → ListCampsAsync 写 _campIndex
    ///   Dictionary 并发写会直接破坏内部结构（抛或静默丢数据）。
    ///   ★ 只锁**字典读写**，**不锁网络请求** —— 否则多营并发会被串行化，
    ///     白白牺牲并发度。
    /// </summary>
    private readonly object _cacheLock = new();

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
        // ★ v1.6.2：「轻课」在 App 内确实是空的，但**公开课不是** ——
        //   myCourseListV2 不传 skyType 会带回 16 个 skuType=OPEN_COURSE 的营
        //   （才艺名师公开课、节气养正公开课、晨练焕醒计划…），它们有 periodId、
        //   能取到课表，可以正常下载。因此「轻课」这个入口改名为「公开课」。
        bool onlyOpenCourse = kind == "公开课";
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
            // 「公开课」入口：只留 OPEN_COURSE 那些（它们无 campId，靠 periodId 取课表）
            if (onlyOpenCourse && camp.SkuType != "OPEN_COURSE") continue;
            camps.Add(camp);
            // 累积式缓存（不清空），便于 camp_info 反查；多次拉不同 tab 会自然合并。
            if (!string.IsNullOrEmpty(camp.Name))
            {
                lock (_cacheLock)
                {
                    // ★ v1.6.2：同名时优先保留**有 campId 的**（付费营）。
                    //   「全部」列表里同名公开课有多个批次（华佗五禽戏…×5），
                    //   让它们顶掉正课会让反查取到错的营。
                    if (!_campIndex.TryGetValue(camp.Name, out var old) || string.IsNullOrEmpty(old.CampId))
                        _campIndex[camp.Name] = camp;
                }
            }
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
        lock (_cacheLock)
        {
            if (_campIndex.TryGetValue(name, out var hit0)) return hit0;
        }
        foreach (var kind in new[] { "正式营", "体验营", "全部" })
        {
            await ListCampsAsync(kind, ct).ConfigureAwait(false);
            lock (_cacheLock)
            {
                if (_campIndex.TryGetValue(name, out var hit)) return hit;
            }
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

        var info = camp;
        // ★ v1.6.2：只有「既没 campId 又没 periodId」才需要反查 ——
        //   公开课 campId 为空但 periodId 有值，直接用它取课表，别去反查（会取到同名营）。
        if (info != null && string.IsNullOrEmpty(info.CampId) && string.IsNullOrEmpty(info.PeriodId))
            info = await EnsureCampAsync(name, ct).ConfigureAwait(false);

        var campId = info?.CampId ?? "";
        var periodId = info?.PeriodId ?? "";

        // ★ 缓存 key 用 campId / periodId 而不是营名 ——
        //   同名营（如「华佗五禽戏·肩脊舒身营-T」有 5 个批次）课表不同，按名字会互相覆盖。
        var key = !string.IsNullOrEmpty(campId) ? "c:" + campId
                : !string.IsNullOrEmpty(periodId) ? "p:" + periodId
                : "n:" + name;
        lock (_cacheLock)
        {
            if (_catalogs.TryGetValue(key, out var cached)) return cached;
        }

        List<Lesson> lessons;
        if (!string.IsNullOrEmpty(campId))
        {
            var data = await _client.PlayListOfCourseAsync(campId, ct).ConfigureAwait(false);
            lessons = ParseLessons(data, info, name);
        }
        else if (!string.IsNullOrEmpty(periodId))
        {
            // ★ v1.6.2：公开课（OPEN_COURSE）没有 campId，用 periodId 走专用端点。
            var data = await _client.OpenCoursePlayListAsync(periodId, ct).ConfigureAwait(false);
            lessons = ParseLessons(data, info, name);
        }
        else
        {
            // 既无 campId 又无 periodId → 没有可用的课表入口
            return new List<Lesson>();
        }

        lock (_cacheLock) { _catalogs[key] = lessons; }
        return lessons;
    }

    /// <summary>课表数组 → Lesson 列表（正课与公开课的字段结构一致，共用）。</summary>
    private static List<Lesson> ParseLessons(JsonElement data, Camp info, string name)
    {
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
        return lessons;
    }

    // ── 播放地址 ──
    public async Task<string> ResolveAsync(Camp camp, Lesson lesson, CancellationToken ct = default)
    {
        var name = camp?.Name ?? lesson?.CampName ?? "";
        var info = camp;
        // ★ v1.6.2：公开课 campId 为空但 periodId 有值 —— **不能按营名反查**
        //   （同名营有多个批次，反查会取到别的营 → 播放地址取错）。
        if (info != null && string.IsNullOrEmpty(info.CampId) && string.IsNullOrEmpty(info.PeriodId))
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
