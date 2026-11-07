using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Xqd.Core;

namespace Xqd.Core.Adb;

/// <summary>
/// ADB 旧路径数据源 —— 实现公共契约 IDataSource。
/// Services.CreateDataSource(DataSourceMode.Adb) 会无参 new 本类。
///
/// 与 API 模式（QianliaoPlatform，直连业务网关）不同，本路径完全靠
/// MuMu 模拟器里的兴趣岛 App UI（uiautomator）+ PlayerCache 隐藏清单取数：
///   ListCampsAsync    → 学习页筛选标签 + 营卡片（滚到底，去重）
///   CampCatalogAsync  → 课程列表页一次 dump 收全课名/日期（课名进列表页时已知）
///   ResolveAsync      → 隐藏清单里 fileId → 播放 URL（缺失/失效则回模拟器重绑）
///   CheckAuthAsync    → 设备/桥接是否在线（ADB 路径不需 Cookie 授权）
///
/// 已验证事实：轻课实测为空（直接返回空列表，绝不探测）；
/// 「学习」页用筛选标签组(≥3 命中)判定；营名 title x≥340；
/// 播放绑 fileId 用清单 mtime 差分；t 约 4.8h 偏移 → 用 HTTP 200/403 实探链接有效性。
/// </summary>
public sealed class AdbDataSource : IDataSource
{
    private readonly AdbDevice _dev;
    private readonly AdbState _state;
    private readonly ManifestCache _cache;

    /// <summary>无参构造：Services 装配点固定 new 本类。</summary>
    public AdbDataSource()
    {
        _dev = new AdbDevice();
        _state = new AdbState();
        _cache = new ManifestCache(_dev, _state);
    }

    public DataSourceMode Mode => DataSourceMode.Adb;

    /// <summary>四个筛选标签（额外便利属性，对照 States.Tabs / IPlatform.CampKinds）。</summary>
    public IReadOnlyList<string> CampKinds => Ui.LearnTabs;

    // ── IDataSource ────────────────────────────────────────────────

    /// <summary>
    /// 列出某标签下的营。对应 xqd_app.list_camps。
    /// ★「轻课」实测为空 → 直接返回空列表，绝不探测（docs/01 三节 / 〇之一）。
    /// ★ 找营必须先把列表滚到底（首屏只有 3~5 个营）。
    /// </summary>
    public async Task<List<Camp>> ListCampsAsync(string kind, CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        kind = kind ?? "";
        if (kind == "轻课") return new List<Camp>();          // 已确认空，直接返回

        string tab = string.IsNullOrEmpty(kind) ? "全部" : kind;
        if (Array.IndexOf(Ui.LearnTabs, tab) < 0) tab = "全部"; // 未知值按「全部」

        var infos = await Task.Run(() =>
        {
            _dev.Connect();
            return _dev.ListCamps(tab, scroll: true);
        }, ct).ConfigureAwait(false);

        var camps = new List<Camp>();
        foreach (var info in infos)
        {
            camps.Add(new Camp
            {
                Name = info.Name,
                // 角标「正式营•共70课」→ 类型 / 节数
                Kind = tab == "全部" ? Ui.BadgeType(info.Badge) : tab,
                Count = Ui.BadgeCount(info.Badge),
                Badge = info.Badge,
                // ADB 旧路径没有业务网关的 campId/periodId/... 等字段，留空
                CampId = "", PeriodId = "", SkuType = "",
                BusinessType = "", BusinessId = "",
            });
        }
        return camps;
    }

    /// <summary>
    /// 采集某营完整课表。对应 xqd.collect_catalog / xqd_app.camp_catalog。
    /// ★ 课名在「进入列表页时」就一次性读到（一次 dump 含整营全部课名），不是播放后反推。
    /// ★ 课表顺序即成品序号（Index 从 0 起）；逐行绑定所属营 CampOfRow。
    /// </summary>
    public async Task<List<Lesson>> CampCatalogAsync(Camp camp, CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        var name = camp?.Name ?? "";
        if (string.IsNullOrEmpty(name)) return new List<Lesson>();

        var cards = await Task.Run(() =>
        {
            _dev.Connect();
            return _dev.CampCatalog(name);
        }, ct).ConfigureAwait(false);

        var lessons = new List<Lesson>();
        var catalog = new List<CatalogEntry>();
        foreach (var c in cards)
        {
            lessons.Add(new Lesson
            {
                Index = c.Index,
                Title = c.Title,
                When = c.When,             // MM.DD HH:MM，与 App 卡片一致
                WhenDate = "",             // ADB 路径无 startTime/年份 → 见「取舍」
                Duration = 0,
                Type = "",
                // 若已做过 sweep，反查把 fileId 绑到已知课名上（供 ResolveAsync）
                FileId = _state.FindFileId(name, c.Title, c.When),
                CampName = name,
                CampOfRow = camp,          // 多营合并时逐行绑定，不按合并行号重排
            });
            catalog.Add(new CatalogEntry { Title = c.Title, When = c.When, Index = c.Index });
        }
        _state.PutCatalog(name, catalog);
        _state.Save();
        return lessons;
    }

    /// <summary>
    /// 返回该节课可直连的清单 URL。对应 xqd_app 的 links.json 反查。
    ///  · 优先用 state 里已绑定的 fileId → links；
    ///  · 用 HTTP 200/403 实探（t 相对服务器时钟约 4.8h 偏移，不能用本地时间推算）；
    ///  · 无缓存或已失效 → 回模拟器重绑：先并缓存清单链接，仍缺则整营 sweep。
    ///    （API 模式不需要 sweep，也没有「链接过期→回模拟器重绑」的问题，见 docs/01 〇之一）
    /// </summary>
    public async Task<string> ResolveAsync(Camp camp, Lesson lesson, CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        string name = camp?.Name ?? lesson?.CampName ?? "";

        string url = _state.FindUrl(name, lesson);
        if (!string.IsNullOrEmpty(url))
        {
            bool alive = await LinkOps.ProbeAliveAsync(url, 15, ct).ConfigureAwait(false);
            if (alive) return url;
        }

        // 轻量兜底：合并缓存里现成链接；仍找不到再整营逐节播放重绑
        await Task.Run(() =>
        {
            _dev.Connect();
            _cache.MergeLinksFromCache(name);
            if (string.IsNullOrEmpty(_state.FindUrl(name, lesson)))
                _cache.SweepCamp(name);
        }, ct).ConfigureAwait(false);

        url = _state.FindUrl(name, lesson);
        if (!string.IsNullOrEmpty(url)) return url;

        throw new InvalidOperationException(
            "未取得播放地址：清单缓存里找不到该课链接（需先执行 sweep 采集）");
    }

    /// <summary>
    /// ADB 路径不依赖 Cookie 授权，检查的是设备/桥接是否在线
    /// （对照 xqd.connect / ensure_device 的「设备在线」语义）。
    /// 不启动模拟器、不读凭据、不发网络请求。
    /// </summary>
    public async Task<(bool Ok, string Message)> CheckAuthAsync(CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        try
        {
            bool ok = await Task.Run(() => _dev.DeviceOnline(), ct).ConfigureAwait(false);
            if (ok) return (true, "设备在线（ADB 桥接 192.168.1.101:5555）");
            return (false, "设备不在线：请确认模拟器已启动且桥接地址可达");
        }
        catch (Exception e)
        {
            return (false, "授权检查失败：" + e.Message);
        }
    }
}
