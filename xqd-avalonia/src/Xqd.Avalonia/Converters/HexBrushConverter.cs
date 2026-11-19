using System;
using System.Globalization;
using Avalonia.Data.Converters;
using Avalonia.Media;

namespace Xqd.Avalonia.Converters;

/// <summary>
/// 十六进制字符串 → 画刷。
/// ★ Core 里的 ViewModel 保持界面无关（只吐 "#RRGGBB"），着色交给这一层，
///   这样同一个 LessonRow 既能给 Avalonia 用，也能给测试用。
/// </summary>
public sealed class HexBrushConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var hex = value as string;
        if (string.IsNullOrWhiteSpace(hex)) return Brushes.Transparent;
        try { return new SolidColorBrush(Color.Parse(hex)); }
        catch { return Brushes.Transparent; }
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is ISolidColorBrush b ? b.Color.ToString() : null;
}
