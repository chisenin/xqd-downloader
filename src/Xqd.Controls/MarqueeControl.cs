using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using Xqd.Core;

namespace Xqd.Gui.Controls;

/// <summary>
/// 课程列表标题里的多营名：中文间隔号「·」分隔，向左无缝循环滚动。
/// 单营 / 短文本不启动定时器（对齐 xqd_gui.MarqueeLabel）。
/// </summary>
public sealed class MarqueeControl : Border
{
    private const double FixedWidth = 250;
    private const double Step = 1;
    private const int IntervalMs = 35;

    private readonly Canvas _canvas = new();
    private readonly TextBlock _tb1 = new();
    private readonly TextBlock _tb2 = new();
    private readonly DispatcherTimer _timer;

    private string _loop = "";
    private double _loopW = 1;
    private double _offset;
    private bool _scroll;

    public string FullText { get; private set; } = "";

    public MarqueeControl()
    {
        Width = FixedWidth;
        ClipToBounds = true;
        Background = Brushes.Transparent;
        VerticalAlignment = VerticalAlignment.Center;
        Child = _canvas;

        foreach (var tb in new[] { _tb1, _tb2 })
        {
            tb.FontFamily = new FontFamily("Microsoft YaHei UI, Microsoft YaHei, Segoe UI, sans-serif");
            tb.FontSize = 13;
            tb.FontWeight = FontWeights.SemiBold;
            tb.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2F3D52"));
            tb.VerticalAlignment = VerticalAlignment.Center;
        }
        _canvas.Children.Add(_tb1);
        _canvas.Children.Add(_tb2);

        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(IntervalMs) };
        _timer.Tick += (_, _) => Tick();
    }

    /// <summary>设置标题文字；<paramref name="scroll"/> 为 true 且文本超宽时才跑马灯。</summary>
    public void SetText(string text, bool scroll, string tooltip = "")
    {
        FullText = text ?? "";
        ToolTip = string.IsNullOrEmpty(tooltip) ? FullText : tooltip;
        _timer.Stop();
        _scroll = false;
        _offset = 0;

        _tb1.Text = FullText;
        Canvas.SetLeft(_tb1, 0);
        _tb2.Visibility = Visibility.Collapsed;

        if (scroll && FullText.Length > 0)
        {
            _loop = FullText + States.CampSeparator;
            _tb1.Text = _loop;
            _tb1.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
            _loopW = Math.Max(1, _tb1.DesiredSize.Width);
            _scroll = _loopW > FixedWidth;
            if (_scroll)
            {
                _tb2.Text = _loop;
                _tb2.Visibility = Visibility.Visible;
                Layout();
                _timer.Start();
            }
        }
    }

    private void Tick()
    {
        if (!_scroll) return;
        _offset = (_offset + Step) % _loopW;
        Layout();
    }

    private void Layout()
    {
        Canvas.SetLeft(_tb1, -_offset);
        Canvas.SetLeft(_tb2, -_offset + _loopW);
    }
}
