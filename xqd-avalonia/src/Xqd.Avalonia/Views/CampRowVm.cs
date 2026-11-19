using Xqd.Core.Ui;

namespace Xqd.Avalonia.Views;

/// <summary>左栏一行：分组小标题（IsHeader）或真实营（Item）。</summary>
public sealed class CampRowVm
{
    public bool IsHeader { get; init; }
    public string Header { get; init; } = "";
    public string HeaderCount { get; init; } = "";
    public CampItem Item { get; init; }
}
