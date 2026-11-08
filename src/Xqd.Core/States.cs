using System;
using System.Collections.Generic;
using System.Linq;

namespace Xqd.Core;

/// <summary>
/// 状态词表 / 布局常量 —— **单一事实来源**。
/// 对应 xqd_gui.py 里的 PHASE_TEXT / PHASE_TEXTS / STATE_TEXTS / STATE_COLORS / COL_*。
/// 三处状态（课名后状态词、下载管理状态列、运行日志）必须共用这一套词。
/// </summary>
public static class States
{
    public const string AppTitle = "兴趣岛视频下载器";
    public const string AppVersion = "1.6.2";   // v1.6.2：公开课可下载 + 营列表按真实营名分组
    /// <summary>产品名基址（不含版本号）。实际 exe 名为 xqd-downloader-vX.Y.Z.exe，
    ///   由 Xqd.Gui.csproj 的 PkgVersion 派生 —— 改版本号不用动这里。</summary>
    public const string ProductExeName = "xqd-downloader";

    // ═══════════════════════════════════════════════════════════
    // v1.6.0：课程列表与下载管理合并为**单表 8 列**。
    // 原来的勾选框列 / 标题前缀列 / 标题后缀列 / 课名后状态词全部删除；
    // 下载管理表的 6 列（TaskCol*）也一并删除 —— 状态与进度并入课程行。
    // 界面与测试一律引用这些常量，不要写死数字。
    // ═══════════════════════════════════════════════════════════
    public const int ColState = 0;      // 状态（胶囊标签）
    public const int ColTitle = 1;      // 课程（课名，宽度最大）
    public const int ColCamp = 2;       // 所属营（单营时隐藏）
    public const int ColDur = 3;        // 时长
    public const int ColSize = 4;       // 大小（右对齐）
    public const int ColSpeed = 5;      // 速度（右对齐）
    public const int ColEta = 6;        // 剩余时间（右对齐）
    public const int ColProgress = 7;   // 进度条 + 百分比
    public const int LessonColumnCount = 8;

    public const string CampSeparator = " · ";

    /// <summary>表头「全选」三态词 —— 单一事实来源（营列表 / 课程表 / 回归测试共用）。</summary>
    public const string CheckNone = "none";
    public const string CheckPartial = "partial";
    public const string CheckAll = "all";

    /// <summary>已勾选 k 个 / 共 n 个 → 表头该显示的状态。</summary>
    public static string CheckAllState(int k, int n) =>
        n <= 0 || k <= 0 ? CheckNone : (k >= n ? CheckAll : CheckPartial);

    public const int MaxLessonWorkers = 3;   // 网络槽位
    public const int SegmentWorkers = 12;    // 每节课内部的分片并发
    public const int MaxMuxWorkers = 2;      // 本地封装槽位
    public static readonly string[] LocalPhases = { "封装", "校验" };
    /// <summary>
    /// 营列表的分类。★ v1.6.2：「轻课」改名「公开课」——
    ///   App 里「轻课」确实是空的，但 myCourseListV2 不传 skyType 会带回
    ///   16 个 skuType=OPEN_COURSE 的公开课营，它们有 periodId、能取到课表，可以下载。
    /// </summary>
    public static readonly string[] Tabs = { "全部", "正式营", "体验营", "公开课" };

    /// <summary>引擎阶段名 → 界面状态词。</summary>
    public static readonly Dictionary<string, string> PhaseText = new()
    {
        ["解析"] = "解析中",
        ["下载"] = "下载中",
        ["封装"] = "封装中",
        ["校验"] = "校验中",
    };

    /// <summary>进行中状态白名单：阶段之间可自由切换，终态不许被覆盖。</summary>
    public static readonly HashSet<string> PhaseTexts = new()
    {
        "下载中", "排队中", "解析中", "封装中", "校验中"
    };

    public static readonly string[] StateTexts =
    {
        "解析中", "下载中", "封装中", "校验中",
        "排队中", "已暂停", "已完成", "失败", "已存在", "需重下",
    };

    public static readonly Dictionary<string, string> StateColors = new()
    {
        ["已完成"] = "#1f7a3d",
        ["失败"] = "#c0392b",
        ["已存在"] = "#7d8b9c",
        ["需重下"] = "#c0392b",
        ["排队中"] = "#8a7ab8",
        ["已暂停"] = "#c07b2a",
        ["下载中"] = "#3b6ea5",
        ["下载中…"] = "#3b6ea5",
        ["解析中"] = "#3b6ea5",
        ["封装中"] = "#c07b2a",
        ["校验中"] = "#8a7ab8",
    };

    public static string ColorOf(string word) =>
        StateColors.TryGetValue(word ?? "", out var c) ? c : "#7d8b9c";

    public static string PhaseWord(string phase) =>
        PhaseText.TryGetValue(phase ?? "", out var w) ? w : phase ?? "";

    public static bool IsRunningWord(string word) => PhaseTexts.Contains(word ?? "");
    public static bool IsTerminalWord(string word) =>
        word == "已完成" || word == "失败" || word == "已存在" || word == "需重下";

    public const string WordQueued = "排队中";
    public const string WordPaused = "已暂停";
    public const string WordDone = "已完成";
    public const string WordFailed = "失败";
    public const string WordExists = "已存在";
    public const string WordRetry = "需重下";

    // ═══════════════════════════════════════════════════════════
    // v1.6.0：状态胶囊配色（底 / 字 / 描边）+ 进度条着色
    // ═══════════════════════════════════════════════════════════

    /// <summary>历史行的统一降级配色（底 / 字 / 描边）。</summary>
    public static readonly string[] HistoryPill = { "#F1F3F6", "#7D8B9C", "#DDE2E9" };

    /// <summary>空闲值占位符 —— 明确表示"这一列现在没数"，比一片空白好认。</summary>
    public const string EmptyDash = "—";

    /// <summary>
    /// 状态词 → 胶囊三色（底 / 字 / 描边）。
    /// ★ 单一事实来源：状态列胶囊、进度条着色都从这里取，漏一个词就少一种配色。
    /// </summary>
    public static readonly Dictionary<string, string[]> StatePills = new()
    {
        ["已完成"] = new[] { "#EAF3DE", "#3B6D11", "#97C459" },
        ["已存在"] = new[] { "#EAF3DE", "#3B6D11", "#97C459" },
        ["下载中"] = new[] { "#E6F1FB", "#185FA5", "#378ADD" },
        ["解析中"] = new[] { "#E6F1FB", "#185FA5", "#378ADD" },
        ["封装中"] = new[] { "#FAEEDA", "#854F0B", "#BA7517" },
        ["校验中"] = new[] { "#FAEEDA", "#854F0B", "#BA7517" },
        ["已暂停"] = new[] { "#FAEEDA", "#854F0B", "#BA7517" },
        ["排队中"] = new[] { "#EEEDFE", "#534AB7", "#7F77DD" },
        ["失败"] = new[] { "#FCEBEB", "#A32D2D", "#E24B4A" },
        ["需重下"] = new[] { "#FCEBEB", "#A32D2D", "#E24B4A" },
    };

    /// <summary>取状态词的胶囊三色；未登记的词用中性灰。</summary>
    public static string[] PillOf(string word) =>
        StatePills.TryGetValue(word ?? "", out var p) ? p : HistoryPill;

    /// <summary>进度条着色：下载中蓝 / 封装中橙 / 完成绿 / 失败红，其余灰蓝。</summary>
    public static string ProgressColorOf(string word)
    {
        switch (word ?? "")
        {
            case "下载中":
            case "解析中":
                return "#3B6EA5";
            case "封装中":
            case "校验中":
            case "已暂停":
                return "#C07B2A";
            case "排队中":
                return "#8A7AB8";
            case "已完成":
                return "#4E9A3E";
            case "已存在":
                return "#7D8B9C";
            case "失败":
            case "需重下":
                return "#C0392B";
            default:
                return "#B9C4D2";
        }
    }

    // ═══════════════════════════════════════════════════════════
    // v1.6.0：视图切换（只过滤显示，**不影响下载范围判定**）
    // ═══════════════════════════════════════════════════════════

    public const string ViewAll = "all";
    public const string ViewPending = "pending";   // 待下载（空闲）
    public const string ViewRunning = "running";   // 下载中（含排队 / 解析 / 封装 / 校验 / 暂停）
    public const string ViewDone = "done";         // 已完成 + 已存在
    public const string ViewFailed = "failed";     // 失败 + 需重下

    public static readonly string[] Views = { ViewAll, ViewPending, ViewRunning, ViewDone, ViewFailed };

    /// <summary>视图键 → 按钮文案。</summary>
    public static string ViewLabel(string view) => view switch
    {
        ViewPending => "待下载",
        ViewRunning => "下载中",
        ViewDone => "已完成",
        ViewFailed => "失败",
        _ => "全部",
    };

    /// <summary>状态词是否算「进行中」（用于「下载中」视图）。</summary>
    public static bool IsRunningState(string word) =>
        word is "下载中" or "解析中" or "封装中" or "校验中" or "排队中" or "已暂停";

    /// <summary>状态词是否算「已完成」（含已存在，用于「已完成」视图）。</summary>
    public static bool IsDoneState(string word) => word is "已完成" or "已存在";

    /// <summary>状态词是否算「失败」（含需重下，用于「失败」视图）。</summary>
    public static bool IsFailedState(string word) => word is "失败" or "需重下";

    /// <summary>
    /// 该状态词在指定视图里是否显示。
    /// ★ 历史行（不在当前课表中）只在「全部」视图出现，且永远不参与下载。
    /// </summary>
    public static bool InView(string view, string word, bool isHistory)
    {
        if (isHistory) return view == ViewAll;
        return view switch
        {
            ViewRunning => IsRunningState(word),
            ViewDone => IsDoneState(word),
            ViewFailed => IsFailedState(word),
            ViewPending => !IsRunningState(word) && !IsDoneState(word) && !IsFailedState(word),
            _ => true,
        };
    }

    /// <summary>
    /// 「下载」按钮的默认范围：待下载 + 失败/需重下（自动重排队重下）。
    /// 已存在 / 已完成 / 进行中 一律跳过。
    /// </summary>
    public static bool InDownloadScope(string word, bool isHistory)
    {
        if (isHistory) return false;
        return !IsRunningState(word) && !IsDoneState(word);
    }
}
