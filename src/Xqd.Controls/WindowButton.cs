using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
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
///
/// ★★ v1.5.4 踩坑记录（别再改回去）：
///   最初用 XamlReader.Parse 解析带 &lt;ControlTemplate.Triggers&gt; 的 XAML 字符串，
///   运行时抛 XamlParseException「无法设置未知成员 ControlTemplate.Triggers」——
///   Triggers 是只读集合属性，XamlReader 的 XamlObjectWriter 不认这个属性元素。
///   异常发生在窗口 Show() 的布局阶段（Measure），**窗口根本创建不出来**，
///   进程活着但没有 HWND，且只在 ~/.xqd_tool/gui-error.log 里留痕。
///   → 现在模板用 FrameworkElementFactory 纯 C# 构建，配色用鼠标事件改 Background，
///     完全不碰 XAML 解析与 Trigger / MultiDataTrigger，编译期类型安全。
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

    // 冻结画刷：悬停/按下事件很频繁，避免每次 new SolidColorBrush。
    private static readonly Brush HoverBrush = Freeze(0x33, 0xFF, 0xFF, 0xFF);
    private static readonly Brush PressBrush = Freeze(0x55, 0x00, 0x00, 0x00);
    private static readonly Brush CloseHoverBrush = Freeze(0xFF, 0xE8, 0x11, 0x23);
    private static readonly Brush ClosePressBrush = Freeze(0xFF, 0xC4, 0x0A, 0x1A);

    private static Brush Freeze(byte a, byte r, byte g, byte b)
    {
        var brush = new SolidColorBrush(Color.FromArgb(a, r, g, b));
        brush.Freeze();
        return brush;
    }

    private Kind _kind = Kind.Minimize;
    private bool _isRestored;
    private bool _hover;
    private bool _pressed;
    // ★ 显式用 System.Windows.Shapes.Path（本文件不 using System.IO，避免撞名）。
    private readonly Path _icon = new();

    /// <summary>XAML 实例化要求无参构造；实际种类由 <see cref="ButtonKind"/> 指定。</summary>
    public WindowButton()
    {
        Width = 44;
        Height = 46;                    // 顶栏 62 - 上下 Margin 8 = 46
        Focusable = false;              // 不参与 Tab 焦点，避免键盘导航到标题栏按钮
        BorderThickness = new Thickness(0);
        Cursor = Cursors.Arrow;
        SnapsToDevicePixels = true;
        Background = Brushes.Transparent;

        _icon.Stroke = Brushes.White;
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

        BuildTemplate();

        // 配色完全靠事件，不用 Trigger —— 与模板解耦，运行时零解析风险。
        MouseEnter += (_, _) => { _hover = true; ApplyBackground(); };
        MouseLeave += (_, _) => { _hover = false; _pressed = false; ApplyBackground(); };
        PreviewMouseLeftButtonDown += (_, _) => { _pressed = true; ApplyBackground(); };
        PreviewMouseLeftButtonUp += (_, _) => { _pressed = false; ApplyBackground(); };

        ApplyIcon();
    }

    /// <summary>
    /// 最简模板：Border（背景绑定到 Button.Background）+ 居中的 ContentPresenter。
    /// 这样 ApplyBackground() 只要改 Button.Background 即可，无需 GetTemplateChild。
    /// </summary>
    private void BuildTemplate()
    {
        var border = new FrameworkElementFactory(typeof(Border));
        border.SetBinding(Border.BackgroundProperty,
            new Binding(nameof(Background)) { RelativeSource = RelativeSource.TemplatedParent });

        var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
        presenter.SetBinding(ContentPresenter.ContentProperty,
            new Binding(nameof(Content)) { RelativeSource = RelativeSource.TemplatedParent });
        presenter.SetValue(HorizontalAlignmentProperty, HorizontalAlignment.Center);
        presenter.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
        border.AppendChild(presenter);

        Template = new ControlTemplate(typeof(WindowButton)) { VisualTree = border };
    }

    /// <summary>
    /// 按钮种类。XAML 在构造之后才设这个属性，所以图标必须在 setter 里重画。
    /// </summary>
    public Kind ButtonKind
    {
        get => _kind;
        set
        {
            if (_kind == value) return;
            _kind = value;
            ApplyIcon();
        }
    }

    /// <summary>最大化状态切换时调用（图标在「最大化」与「还原」之间切换）。</summary>
    public void SetRestoreState(bool isRestored)
    {
        if (_kind != Kind.Maximize) return;
        _isRestored = isRestored;
        ApplyIcon();
    }

    private void ApplyBackground()
    {
        if (_kind == Kind.Close && (_hover || _pressed))
            Background = _pressed ? ClosePressBrush : CloseHoverBrush;
        else if (_pressed)
            Background = PressBrush;
        else if (_hover)
            Background = HoverBrush;
        else
            Background = Brushes.Transparent;
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
                _icon.Data = _isRestored ? RestoreGeometry() : MaximizeGeometry();
                ToolTip = _isRestored ? "还原" : "最大化";
                break;
            case Kind.Close:
                var g = new GeometryGroup();
                g.Children.Add(new LineGeometry(new Point(0.5, 0.5), new Point(9.5, 9.5)));
                g.Children.Add(new LineGeometry(new Point(9.5, 0.5), new Point(0.5, 9.5)));
                _icon.Data = g;
                ToolTip = "关闭";
                break;
        }
        ApplyBackground();
    }

    // ── 矢量几何（10x10 视区，线宽 1）────────────────────────
    private static Geometry MaximizeGeometry()
    {
        var g = new GeometryGroup();
        g.Children.Add(new LineGeometry(new Point(0.5, 0.5), new Point(9.5, 0.5)));
        g.Children.Add(new LineGeometry(new Point(9.5, 0.5), new Point(9.5, 9.5)));
        g.Children.Add(new LineGeometry(new Point(9.5, 9.5), new Point(0.5, 9.5)));
        g.Children.Add(new LineGeometry(new Point(0.5, 9.5), new Point(0.5, 0.5)));
        return g;
    }

    private static Geometry RestoreGeometry()
    {
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
