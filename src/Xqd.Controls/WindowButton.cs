using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Shapes;

namespace Xqd.Gui.Controls;

/// <summary>
/// 无边框窗口的标题栏按钮（最小化 / 最大化-还原 / 关闭）。
///
/// ★ 为什么自绘：去掉 Windows 原生标题栏后，系统按钮就没了，
///   必须在顶栏自己补一组，否则用户找不到关闭入口。
/// ★ 图标全部用 <see cref="Path"/> 画矢量线，**不引图片资源**——
///   避免多资源文件、避免 exe 体积膨胀、避免 CI 里资源路径问题。
/// ★ 控件自带 ControlTemplate（不依赖 Theme.xaml 里的样式），
///   保证在任何引用它的窗口里外观一致。
/// </summary>
public sealed class WindowButton : Button
{
    /// <summary>按钮种类。</summary>
    public enum Kind
    {
        Minimize,
        Maximize,
        Close,
    }

    private Kind _kind;
    // ★ 显式限定 System.Windows.Shapes.Path —— 否则会撞上 System.IO.Path。
    private readonly Path _icon = new();

    /// <summary>XAML 实例化用的无参构造（默认「最小化」）。
    ///   XAML 里的控件必须有无参构造函数，否则编译器报 MC3054。
    ///   实际使用时通过 XAML 的 Kind 属性设置种类。</summary>
    public WindowButton() : this(Kind.Minimize) { }

    public WindowButton(Kind kind)
    {
        _kind = kind;

        Width = 44;
        Height = 46;
        Focusable = false;          // 不参与 Tab 焦点，避免键盘导航到标题栏按钮
        Background = Brushes.Transparent;
        BorderThickness = new Thickness(0);
        Cursor = System.Windows.Input.Cursors.Arrow;
        SnapsToDevicePixels = true;
        Tag = kind == Kind.Close ? "close" : "normal";   // 供模板触发器区分关闭按钮
        ToolTip = kind switch
        {
            Kind.Minimize => "最小化",
            Kind.Maximize => "最大化",
            _ => "关闭",
        };

        _icon.Stroke = new SolidColorBrush(Colors.White);
        _icon.StrokeThickness = 1;
        _icon.StrokeStartLineCap = PenLineCap.Round;
        _icon.StrokeEndLineCap = PenLineCap.Round;
        _icon.Fill = Brushes.Transparent;
        _icon.Stretch = Stretch.None;
        _icon.Width = 10;
        _icon.Height = 10;
        _icon.HorizontalAlignment = HorizontalAlignment.Center;
        _icon.VerticalAlignment = VerticalAlignment.Center;

        Content = _icon;

        // ★ 自绘模板：用 XAML 字符串声明，触发器负责悬停/按下配色。
        //   关闭按钮靠 Tag="close" 区分（MultiDataTrigger 才能同时判两个条件）。
        const string Tpl = @"
<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'
                 xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml'>
  <Border Background='Transparent'>
    <ContentPresenter HorizontalAlignment='Center' VerticalAlignment='Center'/>
    <ControlTemplate.Triggers>
      <Trigger Property='IsMouseOver' Value='true'>
        <Setter Property='Background' Value='#33FFFFFF'/>
      </Trigger>
      <Trigger Property='IsPressed' Value='true'>
        <Setter Property='Background' Value='#55000000'/>
      </Trigger>
      <MultiDataTrigger>
        <MultiDataTrigger.Conditions>
          <Condition Binding='{Binding RelativeSource={RelativeSource Self}, Path=Tag}' Value='close'/>
          <Condition Binding='{Binding RelativeSource={RelativeSource Self}, Path=IsMouseOver}' Value='true'/>
        </MultiDataTrigger.Conditions>
        <Setter Property='Background' Value='#FFE81123'/>
      </MultiDataTrigger>
      <MultiDataTrigger>
        <MultiDataTrigger.Conditions>
          <Condition Binding='{Binding RelativeSource={RelativeSource Self}, Path=Tag}' Value='close'/>
          <Condition Binding='{Binding RelativeSource={RelativeSource Self}, Path=IsPressed}' Value='true'/>
        </MultiDataTrigger.Conditions>
        <Setter Property='Background' Value='#FFC40A1A'/>
      </MultiDataTrigger>
    </ControlTemplate.Triggers>
  </Border>
</ControlTemplate>";
        try
        {
            Template = (ControlTemplate)XamlReader.Parse(Tpl);
        }
        catch (Exception ex)
        {
            // 模板解析失败不至于让整个窗口起不来 —— 退回默认按钮外观。
            System.Diagnostics.Debug.WriteLine("WindowButton 模板解析失败：" + ex.Message);
        }

        ApplyIcon();
    }

    /// <summary>
    /// 按钮种类。XAML 通过这个属性设置（构造函数先跑，XAML 再设属性，
    /// 所以图标必须在 setter 里重画，不能只在构造函数里画）。
    /// </summary>
    public Kind ButtonKind
    {
        get => _kind;
        set
        {
            if (_kind == value) return;
            _kind = value;
            Tag = value == Kind.Close ? "close" : "normal";
            ApplyIcon();
        }
    }

    /// <summary>最大化状态切换时调用（图标在「最大化」与「还原」之间切换）。</summary>
    public void SetRestoreState(bool isRestored)
    {
        if (_kind != Kind.Maximize) return;
        _icon.Data = isRestored ? RestoreGeometry() : MaximizeGeometry();
        ToolTip = isRestored ? "还原" : "最大化";
    }

    /// <summary>按当前种类重画图标与提示文字。</summary>
    private void ApplyIcon()
    {
        switch (_kind)
        {
            case Kind.Minimize:
                _icon.Data = new LineGeometry(new Point(0.5, 5), new Point(9.5, 5));
                ToolTip = "最小化";
                break;
            case Kind.Maximize:
                _icon.Data = MaximizeGeometry();
                ToolTip = "最大化";
                break;
            case Kind.Close:
                var g = new GeometryGroup();
                g.Children.Add(new LineGeometry(new Point(0.5, 0.5), new Point(9.5, 9.5)));
                g.Children.Add(new LineGeometry(new Point(9.5, 0.5), new Point(0.5, 9.5)));
                _icon.Data = g;
                ToolTip = "关闭";
                break;
        }
    }

    // ── 矢量几何（10x10 视区，线宽 1）────────────────────────
    private static Geometry MaximizeGeometry()
    {
        // 方框（最大化）：四条边
        var g = new GeometryGroup();
        g.Children.Add(new LineGeometry(new Point(0.5, 0.5), new Point(9.5, 0.5)));
        g.Children.Add(new LineGeometry(new Point(9.5, 0.5), new Point(9.5, 9.5)));
        g.Children.Add(new LineGeometry(new Point(9.5, 9.5), new Point(0.5, 9.5)));
        g.Children.Add(new LineGeometry(new Point(0.5, 9.5), new Point(0.5, 0.5)));
        return g;
    }

    private static Geometry RestoreGeometry()
    {
        // 两个错位方框（还原）
        var g = new GeometryGroup();
        g.Children.Add(new LineGeometry(new Point(0.5, 2.5), new Point(7.5, 2.5)));
        g.Children.Add(new LineGeometry(new Point(7.5, 2.5), new Point(7.5, 9.5)));
        g.Children.Add(new LineGeometry(new Point(7.5, 9.5), new Point(0.5, 9.5)));
        g.Children.Add(new LineGeometry(new Point(0.5, 9.5), new Point(0.5, 2.5)));
        g.Children.Add(new LineGeometry(new Point(2.5, 2.5), new Point(2.5, 0.5)));
        g.Children.Add(new LineGeometry(new Point(2.5, 0.5), new Point(9.5, 0.5)));
        g.Children.Add(new LineGeometry(new Point(9.5, 0.5), new Point(9.5, 7.5)));
        return g;
    }
}
