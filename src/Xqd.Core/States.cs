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
    public const string AppVersion = "1.5.3";   // v1.5.3：双语言合并 + GitHub Actions 发版
    public const string ProductExeName = "xingqudao-downloader";

    // 课程列表 6 列（v1.5.0 起）。界面与测试一律引用这些常量。
    public const int ColCheck = 0;
    public const int ColPrefix = 1;
    public const int ColTitle = 2;
    public const int ColSuffix = 3;
    public const int ColDur = 4;
    public const int ColProgress = 5;
    public const int LessonColumnCount = 6;

    // 下载管理 6 列
    public const int TaskColState = 0;
    public const int TaskColTitle = 1;
    public const int TaskColSize = 2;
    public const int TaskColSpeed = 3;
    public const int TaskColEta = 4;
    public const int TaskColProgress = 5;
    public const int TaskColumnCount = 6;

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
    public static readonly string[] Tabs = { "全部", "正式营", "体验营", "轻课" };

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
}
