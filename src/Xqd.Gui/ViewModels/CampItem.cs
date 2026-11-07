using System;
using Xqd.Core;

namespace Xqd.Gui.ViewModels;

/// <summary>左栏营列表一行：可勾选、表头「全选」三态、点文字只增不减地勾上。</summary>
public sealed class CampItem : NotifyBase
{
    private bool _isChecked;

    public CampItem(Camp camp)
    {
        Camp = camp;
        Key = string.IsNullOrEmpty(camp.CampId) ? camp.Name : camp.CampId;
        Display = camp.Name + "    " + camp.Badge;
        ToolTip = camp.Name + "（" + camp.Badge + "）\n点营名文字 = 加入课程列表；点前面的方框 = 勾选 / 取消";
    }

    public Camp Camp { get; }
    public string Key { get; }
    public string Display { get; }
    public string ToolTip { get; }

    /// <summary>用户勾选状态变化时通知主窗口（程序批量设置请用 SetCheckedSilently）。</summary>
    public Action<CampItem> CheckChanged;

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
}
