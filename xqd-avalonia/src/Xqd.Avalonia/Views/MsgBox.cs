using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;

namespace Xqd.Avalonia.Views;

/// <summary>
/// 轻量对话框（确认 / 提示）。Avalonia 没有内置 MessageBox，自己画一个，
/// 风格与主窗口一致，避免弹系统原生框破坏观感。
/// </summary>
public static class MsgBox
{
    public static async System.Threading.Tasks.Task<bool> ConfirmAsync(
        Window owner, string title, string message, string okText = "确定", string cancelText = "取消")
    {
        var win = Build(title, message, okText, cancelText, true);
        return await win.ShowDialog<bool>(owner);
    }

    public static async System.Threading.Tasks.Task InfoAsync(
        Window owner, string title, string message, string okText = "知道了")
    {
        var win = Build(title, message, okText, null, false);
        await win.ShowDialog<bool>(owner);
    }

    private static Window Build(string title, string message, string okText,
                                string cancelText, bool twoButtons)
    {
        var root = new StackPanel { Margin = new Thickness(20, 18, 20, 16), Spacing = 14 };

        root.Children.Add(new TextBlock
        {
            Text = title,
            FontSize = 15,
            FontWeight = FontWeight.SemiBold,
            Foreground = new SolidColorBrush(Color.Parse("#1F2937")),
        });
        root.Children.Add(new TextBlock
        {
            Text = message,
            FontSize = 13,
            TextWrapping = TextWrapping.Wrap,
            MaxWidth = 460,
            Foreground = new SolidColorBrush(Color.Parse("#44505F")),
        });

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Spacing = 8,
        };

        var win = new Window
        {
            Title = title,
            SizeToContent = SizeToContent.WidthAndHeight,
            CanResize = false,
            SystemDecorations = SystemDecorations.BorderOnly,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Background = new SolidColorBrush(Color.Parse("#F4F6FA")),
        };

        if (twoButtons)
        {
            var cancel = new Button { Content = cancelText ?? "取消", MinWidth = 84 };
            cancel.Click += (_, _) => win.Close(false);
            buttons.Children.Add(cancel);
        }

        var ok = new Button
        {
            Content = okText,
            MinWidth = 84,
            Background = new SolidColorBrush(Color.Parse("#2F6FB2")),
            Foreground = Brushes.White,
            BorderBrush = new SolidColorBrush(Color.Parse("#2A64A0")),
        };
        ok.Click += (_, _) => win.Close(true);
        buttons.Children.Add(ok);

        root.Children.Add(buttons);
        win.Content = root;
        return win;
    }
}
