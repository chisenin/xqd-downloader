using System;
using Xqd.Core;

namespace Xqd.Gui.ViewModels;

/// <summary>
/// 右栏单表的一行。★ v1.6.0：课程列表与下载管理合并为**一张表**，
/// 行 = 一节课（<see cref="LessonRow"/> 是唯一事实来源），任务信息作为该行的附加列。
///
/// 8 列：状态（胶囊标签）/ 课程 / 所属营 / 时长 / 大小 / 速度 / 剩余 / 进度。
/// 课名后的方括号状态词、勾选框、标题前缀列与标题后缀列**全部删除** ——
/// 序号与日期照旧写进成品文件名，只是不在界面上显示。
///
/// 另有一种**历史行**：上次下载过、但不在当前课表里的课。
/// 它追加在表尾、灰色显示、不可下载、不参与下载范围判定。
/// </summary>
public sealed class LessonRow : NotifyBase
{
    private string _stateWord = "";
    private int _progress;
    private string _progressTip = "";
    private string _toolTip = "";
    private string _size = States.EmptyDash;
    private string _speed = States.EmptyDash;
    private string _eta = States.EmptyDash;
    private bool _isHistory;

    public LessonRow(Lesson lesson, Camp camp, int seq)
    {
        Lesson = lesson;
        CampOfRow = camp;
        Seq = seq;
        Key = (camp?.Name ?? "") + "|" + (lesson?.Key ?? "") + "|" + (lesson?.Title ?? "") + "|" + (lesson?.Index ?? 0);
        Title = lesson?.Title ?? "";
        CampName = camp?.Name ?? lesson?.CampName ?? "";
        Duration = FmtDurationColumn(lesson?.Duration ?? 0);
        ToolTip = (lesson?.Title ?? "") + "\n营：" + CampName +
                  "\n时间：" + (string.IsNullOrEmpty(lesson?.When) ? "-" : lesson.When) +
                  "\n类型：" + (string.IsNullOrEmpty(lesson?.Type) ? "-" : lesson.Type) +
                  "\n时长：" + Duration;
    }

    /// <summary>
    /// 由历史记录构造一行（上次下载过、但不在当前课表里）。
    /// 没有 Lesson / Camp 对象，营名与成品路径来自历史记录。
    /// </summary>
    public static LessonRow FromHistory(HistoryRecord h)
    {
        var row = new LessonRow(null, null, 0)
        {
            IsHistory = true,
            Title = h?.title ?? "",
            CampName = h?.camp ?? "",
            OutPath = h?.path ?? "",
            Duration = FmtDurationColumn(h?.duration ?? 0),
            StateWord = h?.state ?? "",
            ToolTip = (h?.title ?? "") + "\n营：" + (h?.camp ?? "") +
                      "\n成品：" + (h?.path ?? "") + "\n上次状态：" + (h?.state ?? ""),
        };
        long total = h?.total ?? 0;
        long down = h?.down ?? 0;
        if (total > 0) row.Progress = (int)Math.Clamp(down * 100.0 / total, 0, 100);
        else if (h?.state == "已完成") row.Progress = 100;
        if (h?.size > 0) row.Size = FmtSize(h.size);
        return row;
    }

    public Lesson Lesson { get; }
    public Camp CampOfRow { get; }
    public string Key { get; }
    public int Seq { get; }
    public string Title { get; private set; }
    public string CampName { get; private set; }
    public string Duration { get; private set; }
    public string OutPath { get; set; } = "";

    /// <summary>是否历史行（不在当前课表中，追加在表尾、不可下载）。</summary>
    public bool IsHistory
    {
        get => _isHistory;
        set { if (Set(ref _isHistory, value)) Raise(nameof(HistoryHint)); }
    }

    /// <summary>历史行的灰色提示（空串 = 普通行）。</summary>
    public string HistoryHint => _isHistory ? "上次下载" : "";

    /// <summary>
    /// 状态词。变化时状态列胶囊三色与进度条颜色一起通知。
    /// </summary>
    public string StateWord
    {
        get => _stateWord;
        set
        {
            if (_stateWord == value) return;
            _stateWord = value ?? "";
            Raise();
            Raise(nameof(StatePillBg));
            Raise(nameof(StatePillFg));
            Raise(nameof(StatePillBorder));
            Raise(nameof(ProgressColor));
        }
    }

    // ── 状态胶囊三色（浅底 + 深字 + 描边）────────────────────────
    private string[] Pill => States.PillOf(_stateWord);

    public string StatePillBg => Pill[0];
    public string StatePillFg => Pill[1];
    public string StatePillBorder => Pill[2];

    /// <summary>进度条着色（下载中蓝 / 封装中橙 / 完成绿 / 失败红）。</summary>
    public string ProgressColor => States.ProgressColorOf(_stateWord);

    /// <summary>进度百分比文本（进度条右侧）。</summary>
    public string ProgressText => _progress.ToString() + "%";

    public int Progress
    {
        get => _progress;
        set
        {
            if (!Set(ref _progress, value)) return;
            Raise(nameof(ProgressText));
            Raise(nameof(ProgressTip));
        }
    }

    public string ProgressTip
    {
        get => _progressTip;
        set => Set(ref _progressTip, value);
    }

    public string ToolTip
    {
        get => _toolTip;
        set => Set(ref _toolTip, value);
    }

    /// <summary>大小列：下载中 "42.0/145 MB"，完成 "128.4 MB"，空闲 "—"。</summary>
    public string Size
    {
        get => _size;
        set => Set(ref _size, Blank(value));
    }

    /// <summary>速度列：空闲 "—"（引擎给的 "--" 也归一成 "—"）。</summary>
    public string Speed
    {
        get => _speed;
        set => Set(ref _speed, Blank(value));
    }

    /// <summary>剩余时间列：空闲 "—"。</summary>
    public string Eta
    {
        get => _eta;
        set => Set(ref _eta, Blank(value));
    }

    /// <summary>空值 / "--" → 空闲占位符 "—"（明确表示"这一列现在没数"）。</summary>
    private static string Blank(string v) =>
        string.IsNullOrEmpty(v) || v == "--" ? States.EmptyDash : v;

    /// <summary>课程「时长」列显示：MM:SS / H:MM:SS（对齐 xqd_gui._fmt_dur，非倒计时格式）。</summary>
    public static string FmtDurationColumn(double sec)
    {
        long s = (long)(sec > 0 ? sec : 0);
        if (s <= 0) return "-";
        long h = s / 3600;
        long m = (s % 3600) / 60;
        long ss = s % 60;
        return h > 0 ? h + ":" + m.ToString("00") + ":" + ss.ToString("00")
                     : m + ":" + ss.ToString("00");
    }

    /// <summary>字节数 → "128.4 MB"（一位小数；&lt;1MB 用 KB）。</summary>
    public static string FmtSize(long bytes)
    {
        if (bytes <= 0) return States.EmptyDash;
        double kb = bytes / 1024.0;
        if (kb < 1024) return kb.ToString("0.0") + " KB";
        double mb = kb / 1024.0;
        if (mb < 1024) return mb.ToString("0.0") + " MB";
        return (mb / 1024.0).ToString("0.00") + " GB";
    }
}
