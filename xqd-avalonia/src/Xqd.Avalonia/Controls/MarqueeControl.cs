using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Threading;

namespace Xqd.Avalonia.Controls;

/// <summary>横向跑马灯（顶栏显示当前正在下载的长课名）。</summary>
public sealed class MarqueeControl : Panel
{
    public static readonly StyledProperty<string> TextProperty =
        AvaloniaProperty.Register<MarqueeControl, string>(nameof(Text), "");

    public static readonly StyledProperty<double> SpeedProperty =
        AvaloniaProperty.Register<MarqueeControl, double>(nameof(Speed), 1.0);

    private readonly TextBlock _label;
    private readonly DispatcherTimer _timer;
    private double _offset;

    public MarqueeControl()
    {
        ClipToBounds = true;
        _label = new TextBlock
        {
            FontSize = 12,
            VerticalAlignment = global::Avalonia.Layout.VerticalAlignment.Center,
            IsHitTestVisible = false,
            TextWrapping = TextWrapping.NoWrap,
        };
        Children.Add(_label);

        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(30) };
        _timer.Tick += (_, _) => Advance();
    }

    public string Text
    {
        get => GetValue(TextProperty);
        set => SetValue(TextProperty, value);
    }

    public double Speed
    {
        get => GetValue(SpeedProperty);
        set => SetValue(SpeedProperty, value);
    }

    protected override void OnPropertyChanged(AvaloniaPropertyChangedEventArgs change)
    {
        base.OnPropertyChanged(change);
        if (change.Property == TextProperty)
        {
            _label.Text = Text ?? "";
            _offset = 0;
            InvalidateArrange();
        }
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        _timer.Start();
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnDetachedFromVisualTree(e);
        _timer.Stop();
    }

    private void Advance()
    {
        double w = _label.Bounds.Width;
        double avail = Bounds.Width;
        if (w <= 0 || avail <= 0) return;
        if (w <= avail)
        {
            if (_offset != 0) { _offset = 0; InvalidateArrange(); }
            return;
        }
        _offset += Speed;
        if (_offset > w) _offset = -w;
        InvalidateArrange();
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        _label.Measure(new Size(double.PositiveInfinity, availableSize.Height));
        var d = _label.DesiredSize;
        return new Size(double.IsInfinity(availableSize.Width) ? d.Width : availableSize.Width, d.Height);
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        var d = _label.DesiredSize;
        _label.Arrange(new Rect(_offset, 0, d.Width, finalSize.Height));
        return finalSize;
    }
}
