using System;
using Xqd.Core;

namespace Xqd.Avalonia.Views;

/// <summary>历史带一行（只读展示，双击打开所在文件夹）。</summary>
public sealed class HistVm
{
    public HistVm(HistoryRecord rec)
    {
        Rec = rec;
        Title = rec.title ?? "";
        Camp = rec.camp ?? "";
        StateWord = rec.state ?? "";
        Path = rec.path ?? "";
        Size = rec.size > 0 ? Xqd.Core.Ui.LessonRow.FmtSize(rec.size) : "";
        When = rec.ts > 0
            ? DateTimeOffset.FromUnixTimeMilliseconds((long)(rec.ts * 1000))
                          .ToLocalTime().ToString("MM-dd HH:mm")
            : "";
    }

    public HistoryRecord Rec { get; }
    public string Title { get; }
    public string Camp { get; }
    public string StateWord { get; }
    public string Size { get; }
    public string Path { get; }
    public string When { get; }
}
