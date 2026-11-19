using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;

namespace Xqd.Avalonia.Controls;

/// <summary>
/// 进度条单元：底槽 + 着色填充 + 居中百分比。
/// ★ 用三个子元素 + Arrange 算宽度，比自绘文字更省事（字体缩放也交给 Avalonia）。
/// </summary>
public sealed class ProgressCell : Panel
{
    public static readonly StyledProperty<int> ValueProperty =
        AvaloniaProperty.Register<ProgressCell, int>(nameof(Value), 0);

    public static readonly StyledProperty<IBrush> FillProperty =
        AvaloniaProperty.Register<ProgressCell, IBrush>(nameof(Fill),
            new SolidColorBrush(Color.Parse("#3B6EA5")));

    private readonly Border _track;
    private readonly Border _fill;
    private readonly TextBlock _label;

    public ProgressCell()
    {
        ClipToBounds = true;
        _track = new Border
        {
            Background = new SolidColorBrush(Color.Parse("#EFF2F7")),
            CornerRadius = new CornerRadius(5),
        };
        _fill = new Border
        {
            Background = Fill,
            CornerRadius = new CornerRadius(5),
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        _label = new TextBlock
        {
            FontSize = 11,
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            Foreground = new SolidColorBrush(Color.Parse("#4A5568")),
            IsHitTestVisible = false,
        };
        Children.Add(_track);
        Children.Add(_fill);
        Children.Add(_label);
    }

    public int Value
    {
        get => GetValue(ValueProperty);
        set => SetValue(ValueProperty, value);
    }

    public IBrush Fill
    {
        get => GetValue(FillProperty);
        set => SetValue(FillProperty, value);
    }

    protected override void OnPropertyChanged(AvaloniaPropertyChangedEventArgs change)
    {
        base.OnPropertyChanged(change);
        if (change.Property == ValueProperty)
        {
            int v = Value;
            _label.Text = v + "%";
            _label.Foreground = v >= 55
                ? Brushes.White
                : new SolidColorBrush(Color.Parse("#4A5568"));
            InvalidateArrange();
        }
        else if (change.Property == FillProperty)
        {
            _fill.Background = Fill;
        }
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        _label.Measure(availableSize);
        return new Size(
            double.IsInfinity(availableSize.Width) ? 150 : availableSize.Width,
            double.IsInfinity(availableSize.Height) ? 18 : availableSize.Height);
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        double pct = Math.Clamp(Value, 0, 100) / 100.0;
        _track.Arrange(new Rect(0, 2, finalSize.Width, Math.Max(0, finalSize.Height - 4)));
        _fill.Arrange(new Rect(0, 2, finalSize.Width * pct, Math.Max(0, finalSize.Height - 4)));
        _label.Arrange(new Rect(0, 0, finalSize.Width, finalSize.Height));
        return finalSize;
    }
}
