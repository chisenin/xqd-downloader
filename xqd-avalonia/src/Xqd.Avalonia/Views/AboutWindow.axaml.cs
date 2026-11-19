using System;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Xqd.Core;

namespace Xqd.Avalonia.Views;

public partial class AboutWindow : Window
{
    public AboutWindow()
    {
        InitializeComponent();
        LblVersionLine.Text = $"版本 {AppInfo.Version}  ·  {AppInfo.RuntimeInfo}";
        LblToolDir.Text = "配置目录：" + Config.ToolDir;
        LblOutDir.Text = "默认下载目录：" + Config.EffectiveOutDir(Config.Load());
    }

    private void BtnClose_Click(object sender, RoutedEventArgs e) => Close();

    private async void BtnCopy_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            string text = $"{States.AppTitle} {AppInfo.Version}\n{AppInfo.RuntimeInfo}\n"
                        + $"配置目录：{Config.ToolDir}\n"
                        + $"下载目录：{Config.EffectiveOutDir(Config.Load())}";
            var clip = TopLevel.GetTopLevel(this)?.Clipboard;
            if (clip != null) await clip.SetTextAsync(text);
            BtnCopy.Content = "已复制 ✓";
        }
        catch (Exception ex)
        {
            BtnCopy.Content = "复制失败：" + ex.Message;
        }
    }
}
