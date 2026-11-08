using System;
using System.Collections.Generic;
using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;
using Xqd.Core;

namespace Xqd.Gui.Controls;

/// <summary>
/// 状态词 → 独立画刷。三处状态（课名后状态词、下载管理状态列）共用
/// <see cref="States.ColorOf"/>，课名保持深色，绝不整格染色。
/// </summary>
[ValueConversion(typeof(string), typeof(Brush))]
public sealed class StateColorConverter : IValueConverter
{
    private static readonly Dictionary<string, Brush> Cache = new(StringComparer.Ordinal);

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var word = value as string ?? "";
        var hex = States.ColorOf(word);
        if (!Cache.TryGetValue(hex, out var b))
        {
            try
            {
                var c = (Color)ColorConverter.ConvertFromString(hex);
                b = new SolidColorBrush(c);
                b.Freeze();
            }
            catch
            {
                b = Brushes.Gray;
            }
            Cache[hex] = b;
        }
        return b;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
