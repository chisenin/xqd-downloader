using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Templates;
using Avalonia.Input;
using Avalonia.Media;

namespace Xqd.Avalonia.Controls;

/// <summary>窗口按钮种类（顶层枚举 —— XAML 里才能直接引用）。</summary>
public enum WindowButtonKind { Minimize, Maximize, Restore, Close }

/// <summary>
/// 自绘的窗口按钮（最小化 / 最大化 / 还原 / 关闭），沿用 hgvd-downloader 的做法。
///
/// ★ 图标是矢量路径自绘，不是文字字形 —— 用 "—" / "□" / "✕" 当图标，
///   字体缺字形时会渲染成豆腐块，而且大小不受控。
/// </summary>
public sealed class WindowButton : Button
{
    public static readonly StyledProperty<WindowButtonKind> KindProperty =
        AvaloniaProperty.Register<WindowButton, WindowButtonKind>(nameof(Kind));

    private bool _hover;

    static WindowButton()
    {
        AffectsRender<WindowButton>(KindProperty);
    }

    public WindowButton()
    {
        Width = 44;
        Height = 34;
        Background = Brushes.Transparent;
        BorderThickness = new Thickness(0);
        Foreground = Brushes.White;
        FontSize = 13;
        Focusable = false;
        Padding = new Thickness(0);
        // 不放任何文字内容 —— 图标在 Render 里画；模板保持透明，
        // 免得默认主题的边框叠在图标上。
        Template = new FuncControlTemplate<Button>((_, _) =>
            new Border { Background = Brushes.Transparent });
    }

    public WindowButtonKind Kind
    {
        get => GetValue(KindProperty);
        set => SetValue(KindProperty, value);
    }

    protected override void OnPointerEntered(PointerEventArgs e)
    {
        base.OnPointerEntered(e);
        _hover = true;
        InvalidateVisual();
    }

    protected override void OnPointerExited(PointerEventArgs e)
    {
        base.OnPointerExited(e);
        _hover = false;
        InvalidateVisual();
    }

    public override void Render(DrawingContext context)
    {
        base.Render(context);

        var bounds = Bounds.Size;
        double cx = bounds.Width / 2.0;
        double cy = bounds.Height / 2.0;
        const double S = 5.0;      // 图标半宽

        // 关闭按钮悬停 → 红底
        if (Kind == WindowButtonKind.Close && _hover)
            context.FillRectangle(new SolidColorBrush(Color.FromArgb(0xC0, 0xE0, 0x50, 0x50)), new Rect(bounds));

        // 其余按钮悬停 → 白色蒙层
        else if (_hover)
            context.FillRectangle(new SolidColorBrush(Color.FromArgb(0x22, 0xFF, 0xFF, 0xFF)), new Rect(bounds));

        var pen = new Pen(Brushes.White, 1.0) { LineCap = PenLineCap.Square };
        switch (Kind)
        {
            case WindowButtonKind.Minimize:
                context.DrawLine(pen, new Point(cx - S, cy + 3), new Point(cx + S, cy + 3));
                break;
            case WindowButtonKind.Maximize:
                context.DrawRectangle(null, pen, new Rect(cx - S, cy - S, S * 2, S * 2));
                break;
            case WindowButtonKind.Restore:
                // 还原：两个错开的方框
                context.DrawRectangle(null, pen, new Rect(cx - S, cy - S + 1.5, S * 2 - 1.5, S * 2 - 1.5));
                context.DrawRectangle(null, pen, new Rect(cx - S + 1.5, cy - S, S * 2 - 1.5, S * 2 - 1.5));
                break;
            default:  // Close
                context.DrawLine(pen, new Point(cx - S, cy - S), new Point(cx + S, cy + S));
                context.DrawLine(pen, new Point(cx + S, cy - S), new Point(cx - S, cy + S));
                break;
        }
    }
}
