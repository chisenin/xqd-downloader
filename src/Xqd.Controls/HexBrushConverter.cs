using System;
using System.Collections.Generic;
using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;

namespace Xqd.Gui.Controls;

/// <summary>
/// 十六进制颜色字符串（"#RRGGBB" / "#AARRGGBB"）→ 画刷。
///
/// ★ v1.6.0 新增：状态列改成**胶囊标签**（浅底 + 深字 + 描边），
///   进度条也要**按状态着色** —— 这两处都从 States 的配色表取十六进制串，
///   统一由本转换器转成画刷，避免每个视图各写一份转换逻辑。
///   按十六进制串缓存画刷（状态词就十来个，缓存命中率极高）。
/// </summary>
[ValueConversion(typeof(string), typeof(Brush))]
public sealed class HexBrushConverter : IValueConverter
{
    private static readonly Dictionary<string, Brush> Cache = new(StringComparer.OrdinalIgnoreCase);

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var hex = value as string ?? "";
        if (string.IsNullOrWhiteSpace(hex)) return Brushes.Transparent;

        if (!Cache.TryGetValue(hex, out var brush))
        {
            try
            {
                var c = (Color)ColorConverter.ConvertFromString(hex);
                brush = new SolidColorBrush(c);
                brush.Freeze();
            }
            catch
            {
                brush = Brushes.Gray;
            }
            Cache[hex] = brush;
        }
        return brush;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
