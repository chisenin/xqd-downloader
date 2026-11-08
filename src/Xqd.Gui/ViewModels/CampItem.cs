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
            // ★ 必须显式写属性名：Raise() 的 [CallerMemberName] 只在 setter 里
            //   恰好等于 "IsChecked"，批量设置方法里会变成方法名，绑定收不到通知。
            Raise(nameof(IsChecked));
            CheckChanged?.Invoke(this);
        }
    }

    /// <summary>
    /// 批量勾选（「全选」/ 刷新恢复）用：只刷界面，不发 CheckChanged（避免逐行重建课表）。
    /// ★ v1.5.2 修复：以前这里调用无参 Raise()，CallerMemberName 变成
    ///   "SetCheckedSilently"，WPF 的 TwoWay 绑定不会刷新 → 数据已勾上、
    ///   界面方框仍是空的（截图里「已勾选 9 个」但下面 9 个框全空）。
    /// </summary>
    public void SetCheckedSilently(bool value)
    {
        _isChecked = value;
        Raise(nameof(IsChecked));
    }
}
