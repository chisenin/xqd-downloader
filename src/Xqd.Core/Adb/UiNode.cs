using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Xml.Linq;

namespace Xqd.Core.Adb;

/// <summary>
/// uiautomator dump 里的一个 &lt;node&gt;。
/// 对应 xqd.py find_nodes 的 {'id','text','x','y','cx','cy','w','h'}。
/// 用 System.Xml.Linq 解析（任务约束：BCL、XDocument，不用正则抠 XML 结构）。
/// </summary>
internal sealed class UiNode
{
    public string Id = "";      // resource-id 全串（如 com.qlchat.xingqudao:id/title）
    public string Rid = "";     // resource-id 末段（如 title / tv_title / rv / courseShowType）
    public string Text = "";    // text 属性 Trim 后
    public string Desc = "";    // content-desc 属性（备用）
    public int X, Y, Cx, Cy, W, H;

    public override string ToString() => $"<UiNode {Rid} '{Text}' ({X},{Y})>";
}

/// <summary>课程列表页的一张卡片（文档顺序扫描的结果）。对应 xqd.list_cards / xqd_app._cards_from_xml。</summary>
internal sealed class Card
{
    public string Title = "";
    public string When = "";     // MM.DD HH:MM
    public int Bx, By;           // 「去学习」按钮中心；0 表示当前在屏幕外（bounds=[0,0][0,0]）
    public bool Visible;
    public int Index;
}

/// <summary>「学习」页的一个营卡片。对应 xqd_app._parse_camps 的 {'name','badge'}。</summary>
internal sealed class CampInfo
{
    public string Name = "";
    public string Badge = "";    // courseShowType 角标，如「正式营•共70课」
}

/// <summary>
/// uiautomator XML 的纯解析层（不涉及任何 adb / 网络调用）。
///
/// 已验证事实（docs/01 三/四/十节）：
///  · 一次 dump 就含整营全部课名；屏幕外节点 bounds=[0,0][0,0]，文本仍可读 → 不能因 bounds 全 0 丢弃节点。
///  · 卡片文档顺序固定：课名 → 日期(MM.DD HH:MM) → ▶图标 → 状态 →「去学习」。
///  · 「学习」页必须用筛选标签组(≥3 命中)判定，不能用营卡片。
///  · 营名 title 在 x≥340；左侧 x&lt;150 的是分组标题；顶部「继续学」横滑要与竖列表去重。
/// </summary>
internal static class Ui
{
    public static readonly string[] LearnTabs = { "全部", "正式营", "体验营", "轻课" };

    // 日期正则（docs/01 四节）：^\d{2}\.\d{2}\s+\d{2}:\d{2}$
    public static readonly Regex DateRe =
        new(@"^\d{2}\.\d{2}\s+\d{2}:\d{2}$", RegexOptions.Compiled);

    private static readonly Regex BoundsRe =
        new(@"^\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]$", RegexOptions.Compiled);

    private static readonly Regex TotalRe =
        new(@"^全部\s*(\d+)$", RegexOptions.Compiled);

    private static readonly Regex BadgeCountRe =
        new(@"共\s*(\d+)\s*课", RegexOptions.Compiled);

    private static readonly Regex BadgeTypeRe =
        new(@"^\s*([^\s•]+)", RegexOptions.Compiled);

    // 纯图标 / 私用区 / 方向控制符 / 空白字符（不能当课名）
    private static readonly Regex IconRe =
        new(@"^[\uE000-\uF8FF\u200F\uFEFF\-\s]+$", RegexOptions.Compiled);

    // 状态/按钮类文案（不能当课名）——对应 xqd.py STATUS_TEXT
    private static readonly HashSet<string> StatusText = new(StringComparer.Ordinal)
    {
        "已学完", "已完课", "未完课", "去学习", "正序", "最近学习", "分享",
        "听课进度", "今日课程", "全部", "联系老师", "排行榜", "排名第1名",
        "正在直播", "课程回放中", "已结束", "直播中", "开始上课", "预约",
        "开启消息通知，不错过上课提醒、点评等消息去开启",
    };

    // ── 基础属性助手 ──────────────────────────────────────────────

    private static string Attr(XElement e, string name) =>
        (string)e.Attribute(name) ?? "";

    private static string RidOf(XElement e)
    {
        var id = Attr(e, "resource-id");
        int i = id.LastIndexOf('/');
        return i >= 0 ? id.Substring(i + 1) : id;
    }

    private static string TxtOf(XElement e) => Attr(e, "text").Trim();

    private static int[] BoundsOf(XElement e)
    {
        var m = BoundsRe.Match(Attr(e, "bounds"));
        if (!m.Success) return null;
        return new[]
        {
            int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value),
            int.Parse(m.Groups[3].Value), int.Parse(m.Groups[4].Value),
        };
    }

    /// <summary>
    /// 解析 dump → 文档顺序的 UiNode 列表，等价于 xqd.find_nodes(xml)。
    /// 注意：bounds 缺失的节点才跳过（Python find_nodes 无 bm 则 continue）；
    /// bounds=[0,0][0,0] 是合法值，必须保留（屏幕外节点文本仍可读）。
    /// </summary>
    public static List<UiNode> FindNodes(string xml)
    {
        var outList = new List<UiNode>();
        if (string.IsNullOrEmpty(xml)) return outList;
        XDocument doc;
        try { doc = XDocument.Parse(xml); }
        catch { return outList; }
        if (doc.Root == null) return outList;

        foreach (var e in doc.Root.DescendantsAndSelf())
        {
            if (e.Name.LocalName != "node") continue;
            var b = BoundsOf(e);
            if (b == null) continue;                 // 与 Python 一致：无 bounds 跳过
            int x1 = b[0], y1 = b[1], x2 = b[2], y2 = b[3];
            var id = Attr(e, "resource-id");
            outList.Add(new UiNode
            {
                Id = id,
                Rid = RidOf(e),
                Text = TxtOf(e),
                Desc = Attr(e, "content-desc"),
                X = x1, Y = y1,
                Cx = (x1 + x2) / 2, Cy = (y1 + y2) / 2,
                W = x2 - x1, H = y2 - y1,
            });
        }
        return outList;
    }

    /// <summary>等价于 xqd.find_nodes(xml, want_text=...)。</summary>
    public static List<UiNode> FindNodes(string xml, string wantText)
    {
        if (wantText == null) return FindNodes(xml);
        return FindNodes(xml).Where(n => n.Text == wantText).ToList();
    }

    // ── 页面识别（docs/01 十节，用特征判定，不靠营卡片） ──────────

    /// <summary>
    /// 是否「学习」页：tv_title 存在 且 四个筛选标签文本命中 ≥3 个。
    /// ★ 必须用筛选标签组判定，空标签时仍成立（轻课为空时不能靠营卡片）。
    /// </summary>
    public static bool IsLearnTab(string xml, List<UiNode> nodes = null)
    {
        if (string.IsNullOrEmpty(xml)) return false;
        nodes = nodes ?? FindNodes(xml);
        bool hasTvTitle = nodes.Any(n => n.Id.IndexOf("tv_title", StringComparison.Ordinal) >= 0);
        if (!hasTvTitle) return false;
        var texts = new HashSet<string>(nodes.Select(n => n.Text), StringComparer.Ordinal);
        int hit = LearnTabs.Count(t => texts.Contains(t));
        return hit >= 3;
    }

    /// <summary>对应 xqd.page_kind 的四个特征分支（player / course_list / learn_list / chat）。</summary>
    public static string PageKind(string xml)
    {
        if (string.IsNullOrEmpty(xml)) return "empty";
        var nodes = FindNodes(xml);
        if (xml.IndexOf("superPlayerView", StringComparison.Ordinal) >= 0 ||
            xml.IndexOf("superplayer_tv_current", StringComparison.Ordinal) >= 0)
            return "player";
        if (xml.IndexOf("nameTv", StringComparison.Ordinal) >= 0 &&
            xml.IndexOf("startTimeTv", StringComparison.Ordinal) >= 0)
            return "player";                     // 播放器「听课列表」
        if (xml.IndexOf("toolbarTitle", StringComparison.Ordinal) >= 0 &&
            xml.IndexOf("去学习", StringComparison.Ordinal) >= 0)
            return "course_list";                // 完整课程列表页（WebView）
        if (xml.IndexOf("全部 ", StringComparison.Ordinal) >= 0 ||
            xml.IndexOf("已完课 ", StringComparison.Ordinal) >= 0)
            return "course_list";
        if (IsLearnTab(xml, nodes)) return "learn_list";
        if (xml.IndexOf("messageContent", StringComparison.Ordinal) >= 0) return "chat";
        return "unknown";
    }

    // ── 学习页：营卡片 / 角标 ─────────────────────────────────────

    /// <summary>对应 xqd._learn_cards：title 节点 x≥340、text 非空、w&gt;120。</summary>
    public static List<UiNode> LearnCards(string xml, List<UiNode> nodes = null)
    {
        nodes = nodes ?? FindNodes(xml);
        return nodes.Where(n => n.Id.EndsWith("/title", StringComparison.Ordinal)
                                && n.X >= 340 && n.Text.Length > 0 && n.W > 120).ToList();
    }

    /// <summary>对应 xqd.camp_cards：(营名文本, x, y) 列表，x/y 为左上角。</summary>
    public static List<(string text, int x, int y)> CampCards(string xml, List<UiNode> nodes = null)
    {
        return LearnCards(xml, nodes)
            .Select(n => (text: n.Text, x: n.X, y: n.Y))
            .ToList();
    }

    /// <summary>角标里的节数（「正式营•共70课」→ 70）。对应 xqd_app._badge_count。</summary>
    public static int BadgeCount(string badge)
    {
        var m = BadgeCountRe.Match(badge ?? "");
        return m.Success && int.TryParse(m.Groups[1].Value, out var n) ? n : 0;
    }

    /// <summary>角标里的类型（「正式营•共70课」→「正式营」）。对应 xqd_app._badge_type。</summary>
    public static string BadgeType(string badge)
    {
        var m = BadgeTypeRe.Match(badge ?? "");
        return m.Success ? m.Groups[1].Value : "";
    }

    /// <summary>
    /// 对应 xqd_app._parse_camps：解析「学习」页 → [(营名, 角标)]，去重且保持顺序。
    ///
    /// 竖列表 = rid 'rv' 且 bounds 宽≥850 高&gt;800 的直接子项（w≥850、h≥90），
    /// 营名取子项里 rid 'title' 且 x≥340、w&gt;120 的节点（避开 x&lt;150 的分组标题）；
    /// 角标取 rid 'courseShowType'。顶部横向「继续学」滑块（非竖 rv 的子项，w≤380、h≥200）
    /// 也加入，但整体按营名去重，避免与竖列表重复。
    /// </summary>
    public static List<CampInfo> ParseCamps(string xml)
    {
        var camps = new List<CampInfo>();
        if (string.IsNullOrEmpty(xml)) return camps;
        XDocument doc;
        try { doc = XDocument.Parse(xml); }
        catch { return camps; }
        if (doc.Root == null) return camps;

        void Add(string name, string badge)
        {
            if (string.IsNullOrEmpty(name)) return;
            foreach (var c in camps)
            {
                if (c.Name == name)
                {
                    if (!string.IsNullOrEmpty(badge) && string.IsNullOrEmpty(c.Badge)) c.Badge = badge;
                    return;                                  // 去重：同名只保留首条
                }
            }
            camps.Add(new CampInfo { Name = name, Badge = badge ?? "" });
        }

        foreach (var rv in doc.Root.DescendantsAndSelf())
        {
            if (RidOf(rv) != "rv") continue;
            var b = BoundsOf(rv);
            bool vertical = b != null && (b[2] - b[0]) >= 850 && (b[3] - b[1]) > 800;

            foreach (var child in rv.Elements())            // 仅直接子项
            {
                var cb = BoundsOf(child);
                if (cb == null) continue;
                int w = cb[2] - cb[0], h = cb[3] - cb[1];

                if (vertical)
                {
                    if (w < 850 || h < 90) continue;
                    string badge = "", name = null;
                    foreach (var d in child.Descendants())   // 等价 xqd_app._iter(child)
                    {
                        var drid = RidOf(d);
                        var dtxt = TxtOf(d);
                        if (drid == "courseShowType") badge = dtxt;
                        else if (drid == "title" && dtxt.Length > 0)
                        {
                            var db = BoundsOf(d);
                            if (db != null && db[0] >= 340 && (db[2] - db[0]) > 120)
                            {
                                name = dtxt;
                                break;
                            }
                        }
                    }
                    if (name != null) Add(name, badge);
                }
                else
                {
                    // 顶部横向「继续学」滑块
                    if (w > 380 || h < 200) continue;
                    foreach (var d in child.Descendants())
                    {
                        var dtxt = TxtOf(d);
                        if (RidOf(d) == "title" && dtxt.Length > 0)
                        {
                            Add(dtxt, "");
                            break;
                        }
                    }
                }
            }
        }
        return camps;
    }

    // ── 课程列表页（WebView）：总数 / 卡片 ─────────────────────────

    /// <summary>「全部 N」→ 该营总节数。对应 xqd.list_total。</summary>
    public static int ListTotal(string xml, List<UiNode> nodes = null)
    {
        nodes = nodes ?? FindNodes(xml);
        foreach (var n in nodes)
        {
            var m = TotalRe.Match(n.Text);
            if (m.Success && int.TryParse(m.Groups[1].Value, out var v)) return v;
        }
        return 0;
    }

    /// <summary>
    /// 解析课程列表页全部卡片（按文档顺序）。对应 xqd.list_cards / xqd_app._cards_from_xml。
    /// ★ 一次 dump 就含整营全部课名：屏幕外节点 bounds=[0,0][0,0] 文本仍可读，照常纳入。
    ///   卡片顺序固定 课名→日期→▶→状态→去学习，靠文档顺序配对，无需靠播放反推。
    ///   「去学习」按钮仅在 y&gt;0（节点在屏内）时记坐标；≤320 的吸顶按钮在 sweep 里跳过。
    /// </summary>
    public static List<Card> ListCards(string xml, List<UiNode> nodes = null)
    {
        nodes = nodes ?? FindNodes(xml);
        var cards = new List<Card>();
        string lastText = "";
        int lastDateIdx = -99;

        foreach (var n in nodes)
        {
            var t = n.Text;
            if (t.Length == 0) continue;

            if (DateRe.IsMatch(t))
            {
                cards.Add(new Card
                {
                    Title = lastText, When = t,
                    Bx = 0, By = 0,
                    Visible = n.Y > 0,
                    Index = cards.Count,
                });
                lastDateIdx = cards.Count - 1;
                lastText = "";
                continue;
            }
            if (t == "去学习")
            {
                // 归属于最近一张日期卡片（限定 12 个节点内，避免误配吸顶悬浮按钮）
                if (lastDateIdx >= 0 && cards.Count - 1 - lastDateIdx <= 12)
                {
                    var c = cards[lastDateIdx];
                    if (c.Bx == 0 && n.Y > 0)
                    {
                        c.Bx = n.Cx; c.By = n.Cy; c.Visible = true;
                    }
                }
                continue;
            }
            if (StatusText.Contains(t) || IconRe.IsMatch(t)) continue;
            if (t.Length > 60) continue;                    // 横幅/提示文案不是课名
            lastText = t;
        }
        return cards;
    }
}
