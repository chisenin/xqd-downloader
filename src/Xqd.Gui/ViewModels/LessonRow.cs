using System;
using Xqd.Core;

namespace Xqd.Gui.ViewModels;

/// <summary>
/// 右栏课程列表一行。6 列：勾选 / 标题前缀（原营内序号，不重排）/ 课程（课名 + 独立配色状态词）
/// / 标题后缀（YYYY.MM.DD）/ 时长 / 进度。每行绑定所属营 CampOfRow。
/// </summary>
public sealed class LessonRow : NotifyBase
{
    private bool _isChecked;
    private string _stateWord = "";
    private int _progress;
    private string _progressTip = "";
    private string _toolTip = "";

    public LessonRow(Lesson lesson, Camp camp, int seq)
    {
        Lesson = lesson;
        CampOfRow = camp;
        Seq = seq;
        Key = (camp?.Name ?? "") + "|" + (lesson?.Key ?? "") + "|" + (lesson?.Title ?? "") + "|" + (lesson?.Index ?? 0);
        Prefix = seq.ToString("00");
        Title = lesson?.Title ?? "";
        Suffix = lesson?.WhenDate ?? "";
        Duration = FmtDurationColumn(lesson?.Duration ?? 0);
        ToolTip = (lesson?.Title ?? "") + "\n营：" + (camp?.Name ?? "") +
                  "\n时间：" + (string.IsNullOrEmpty(lesson?.When) ? "-" : lesson.When) +
                  "\n类型：" + (string.IsNullOrEmpty(lesson?.Type) ? "-" : lesson.Type) +
                  "\n时长：" + Duration;
    }

    public Lesson Lesson { get; }
    public Camp CampOfRow { get; }
    public string Key { get; }
    public int Seq { get; }
    public string Prefix { get; }
    public string Title { get; }
    public string Suffix { get; }
    public string Duration { get; }
    public string OutPath { get; set; } = "";

    /// <summary>状态词变化时 StateSuffix 一起通知，DataTemplate 里两个文本块独立配色。</summary>
    public string StateWord
    {
        get => _stateWord;
        set
        {
            if (_stateWord == value) return;
            _stateWord = value ?? "";
            Raise();
            Raise(nameof(StateSuffix));
        }
    }

    /// <summary>紧跟课名的方括号状态词（课名列第二个 TextBlock 绑定它）。</summary>
    public string StateSuffix => string.IsNullOrEmpty(_stateWord) ? "" : "  [" + _stateWord + "]";

    public int Progress
    {
        get => _progress;
        set { if (Set(ref _progress, value)) Raise(nameof(ProgressTip)); }
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

    public Action<LessonRow> CheckChanged;

    public bool IsChecked
    {
        get => _isChecked;
        set
        {
            if (_isChecked == value) return;
            _isChecked = value;
            Raise();
            CheckChanged?.Invoke(this);
        }
    }

    public void SetCheckedSilently(bool value)
    {
        _isChecked = value;
        Raise();
    }

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
}
