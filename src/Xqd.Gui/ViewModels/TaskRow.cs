namespace Xqd.Gui.ViewModels;

/// <summary>
/// 下载管理表一行。列顺序严格按 States.TaskCol*：
/// 状态 / 课名 / 大小 / 速度 / 剩余时间 / 进度。
/// 状态词由 States.PhaseWord / 状态词表驱动，独立配色。
/// 没有独立勾选列 —— 删除对象来自 ListView 的选中行。
/// </summary>
public sealed class TaskRow : NotifyBase
{
    private string _stateWord = "";
    private string _title = "";
    private string _size = "";
    private string _speed = "--";
    private string _eta = "--";
    private double _progress;

    public string OutPath { get; set; } = "";
    public int? JobId { get; set; }
    public string ToolTip { get; set; } = "";

    public string StateWord
    {
        get => _stateWord;
        set => Set(ref _stateWord, value ?? "");
    }

    public string Title
    {
        get => _title;
        set => Set(ref _title, value ?? "");
    }

    public string Size
    {
        get => _size;
        set => Set(ref _size, value ?? "");
    }

    public string Speed
    {
        get => _speed;
        set => Set(ref _speed, value ?? "--");
    }

    public string Eta
    {
        get => _eta;
        set => Set(ref _eta, value ?? "--");
    }

    public double Progress
    {
        get => _progress;
        set => Set(ref _progress, value);
    }
}
