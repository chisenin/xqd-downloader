using System;

namespace Xqd.Core.Ui;

/// <summary>
/// 左栏营列表一行：可勾选、点文字只增不减地勾上。
/// 按真实营名列出，并按「已购课程 / 公开课」分组。
/// 公开课（skuType=OPEN_COURSE）没有 campId，靠 periodId 取课表。
/// </summary>
public sealed class CampItem : NotifyBase
{
    private bool _isChecked;

    /// <summary>同名营的批次序号（同名时第 2 个起显示「(2)」）。</summary>
    private readonly int _sameNameSeq;

    public CampItem(Camp camp, int sameNameSeq = 1)
    {
        Camp = camp;
        _sameNameSeq = sameNameSeq;
        // ★ Key 必须能唯一区分同名营 —— 公开课没有 campId，
        //   若退回用 Name，5 个同名公开课会共用一个 Key，勾选状态就会串。
        Key = !string.IsNullOrEmpty(camp.CampId) ? camp.CampId
            : !string.IsNullOrEmpty(camp.PeriodId) ? camp.PeriodId
            : camp.Name;
        Display = sameNameSeq > 1 ? camp.Name + " (" + sameNameSeq + ")" : camp.Name;
        Badge = camp.Badge;
        IsOpenCourse = camp.SkuType == "OPEN_COURSE";
        GroupKey = IsOpenCourse ? "公开课" : "已购课程";
        ToolTip = camp.Name + "（" + camp.Badge + "）" +
                  (IsOpenCourse ? "\n公开课：用 periodId 取课表，可正常下载" : "") +
                  "\n点营名文字 = 加入课程列表；点前面的方框 = 勾选 / 取消";
    }

    public Camp Camp { get; }
    public string Key { get; }
    public string Display { get; }
    public string Badge { get; }
    /// <summary>分组键（"已购课程" / "公开课"）—— 列表按它显示分组小标题。</summary>
    public string GroupKey { get; }
    /// <summary>是否公开课（公开课无 campId，靠 periodId 取课表）。</summary>
    public bool IsOpenCourse { get; }
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
            // ★ 必须显式写属性名：CallerMemberName 在批量设置方法里会变成方法名，
            //   绑定收不到通知。
            Raise(nameof(IsChecked));
            CheckChanged?.Invoke(this);
        }
    }

    /// <summary>
    /// 批量勾选（「全选」/ 刷新恢复）用：只刷界面，不发 CheckChanged（避免逐行重建课表）。
    /// ★ 必须显式 Raise(nameof(IsChecked))，否则界面方框不刷新。
    /// </summary>
    public void SetCheckedSilently(bool value)
    {
        _isChecked = value;
        Raise(nameof(IsChecked));
    }
}
