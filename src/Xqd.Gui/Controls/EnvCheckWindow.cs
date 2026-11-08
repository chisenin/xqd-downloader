using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using Xqd.Core;
using Xqd.Core.Setup;

namespace Xqd.Gui.Controls;

/// <summary>
/// ★ v1.6.3：运行环境检查对话框。
///
/// 首次启动（或用户手动点「环境检查」）时列出依赖状态：
///   · ffmpeg / ffprobe —— 致命依赖，缺失时提供**一键自动下载安装**
///   · MuMu 模拟器 —— 可选，仅首次授权需要，缺失只给官网链接
///
/// 下载源优先走**非 GitHub 的国内 CDN**（npmmirror），不行再退到
/// ffmpeg 官方构建站，最后才用带代理的 GitHub 源（详见 DependencyInstaller）。
/// </summary>
public sealed class EnvCheckWindow : Window
{
    private readonly List<DepCheckResult> _items = new();
    private readonly TextBlock _summary = new();
    private readonly StackPanel _list = new();
    private readonly ProgressBar _bar = new() { Height = 8, Minimum = 0, Maximum = 100, Visibility = Visibility.Collapsed };
    private readonly TextBlock _stage = new();
    private readonly Button _install = new();
    private readonly Button _close = new();
    private readonly Button _mumuLink = new();
    private CancellationTokenSource _cts = new();

    private static Brush BrushOf(string hex) =>
        new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex));

    public EnvCheckWindow(Window owner, bool autoCloseWhenAllOk)
    {
        Owner = owner;
        Title = "运行环境检查";
        Width = 640;
        Height = 520;
        MinWidth = 520;
        MinHeight = 420;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Background = BrushOf("#F4F6FA");
        FontFamily = new FontFamily("Microsoft YaHei UI, Microsoft YaHei, Segoe UI, sans-serif");
        Foreground = BrushOf("#2B3445");

        var root = new Grid { Margin = new Thickness(14, 12, 14, 12) };
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        // ── 标题 ──
        var title = new TextBlock
        {
            Text = "运行环境检查",
            FontSize = 16,
            FontWeight = FontWeights.SemiBold,
            Margin = new Thickness(2, 0, 0, 8),
        };
        Grid.SetRow(title, 0);
        root.Children.Add(title);

        // ── 摘要 ──
        _summary.TextWrapping = TextWrapping.Wrap;
        _summary.Foreground = BrushOf("#4A5A72");
        _summary.Margin = new Thickness(2, 0, 0, 10);
        Grid.SetRow(_summary, 1);
        root.Children.Add(_summary);

        // ── 依赖列表 ──
        var scroll = new ScrollViewer
        {
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            Background = Brushes.White,
            BorderBrush = BrushOf("#E0E5EE"),
            BorderThickness = new Thickness(1),
            Padding = new Thickness(10),
        };
        scroll.Content = _list;
        Grid.SetRow(scroll, 2);
        root.Children.Add(scroll);

        // ── 进度 ──
        var prog = new StackPanel { Margin = new Thickness(2, 10, 2, 0) };
        _stage.TextWrapping = TextWrapping.Wrap;
        _stage.FontSize = 12;
        _stage.Foreground = BrushOf("#4A5A72");
        _stage.Margin = new Thickness(0, 0, 0, 5);
        prog.Children.Add(_stage);
        prog.Children.Add(_bar);
        Grid.SetRow(prog, 3);
        root.Children.Add(prog);

        // ── MuMu 官网链接（仅缺失时显示）──────────────────────
        _mumuLink.Content = "打开 MuMu 模拟器官网下载";
        _mumuLink.Width = 220;
        _mumuLink.Height = 30;
        _mumuLink.HorizontalAlignment = HorizontalAlignment.Left;
        _mumuLink.Margin = new Thickness(2, 8, 0, 0);
        _mumuLink.Visibility = Visibility.Collapsed;
        _mumuLink.Click += (_, _) =>
        {
            try
            {
                Process.Start(new ProcessStartInfo("https://www.mumuplayer.com/download/")
                { UseShellExecute = true });
            }
            catch { /* 打不开就算了，官网地址已写在提示里 */ }
        };
        Grid.SetRow(_mumuLink, 4);
        root.Children.Add(_mumuLink);

        // ── 按钮 ──
        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(0, 12, 0, 0),
        };
        _install.Content = "立即下载安装";
        _install.Width = 140;
        _install.Height = 32;
        _install.Margin = new Thickness(0, 0, 8, 0);
        _install.Background = BrushOf("#3B6EA5");
        _install.Foreground = Brushes.White;
        _install.BorderThickness = new Thickness(0);
        _install.Cursor = System.Windows.Input.Cursors.Hand;
        _install.Click += async (_, _) => await RunInstallAsync();
        buttons.Children.Add(_install);

        _close.Content = "关闭";
        _close.Width = 90;
        _close.Height = 32;
        _close.Background = Brushes.White;
        _close.Foreground = BrushOf("#2B3445");
        _close.BorderBrush = BrushOf("#D5DCE8");
        _close.BorderThickness = new Thickness(1);
        _close.Cursor = System.Windows.Input.Cursors.Hand;
        _close.Click += (_, _) => Close();
        buttons.Children.Add(_close);
        Grid.SetRow(buttons, 5);
        root.Children.Add(buttons);

        Content = root;

        Refresh();

        // 首次启动：全齐就自动关掉，不打扰用户
        if (autoCloseWhenAllOk && !DependencyCheck.HasMissingRequired(_items))
        {
            Dispatcher.BeginInvoke(new Action(() => Close()), DispatcherPriority.Background);
        }
    }

    /// <summary>重新跑一次检查并刷新界面。</summary>
    public void Refresh()
    {
        _items.Clear();
        _items.AddRange(DependencyCheck.CheckAll());

        _list.Children.Clear();
        foreach (var r in _items) _list.Children.Add(BuildRow(r));

        int missing = _items.Count(r => r.Required && !r.Ok);
        bool mumuMissing = _items.Any(r => r.Id == "mumu" && !r.Ok);

        _summary.Text = missing == 0
            ? "依赖齐全，可以正常下载与合并课程视频。"
            : $"缺少 {missing} 项必需依赖 —— 没有它们，分片无法合并成可播放的 MP4。"
              + "点「立即下载安装」即可自动获取（国内镜像优先）。";

        _install.Visibility = missing > 0 ? Visibility.Visible : Visibility.Collapsed;
        _mumuLink.Visibility = mumuMissing ? Visibility.Visible : Visibility.Collapsed;
    }

    private UIElement BuildRow(DepCheckResult r)
    {
        var grid = new Grid { Margin = new Thickness(0, 4, 0, 4) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(26) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

        // 状态图标：● / ○
        var icon = new TextBlock
        {
            Text = r.Ok ? "●" : "○",
            FontSize = 14,
            VerticalAlignment = VerticalAlignment.Center,
            Foreground = BrushOf(r.Ok ? (r.Required ? "#1F7A3D" : "#8494A8") : "#B03030"),
            ToolTip = r.Ok ? "已就绪" : "缺失",
        };
        Grid.SetColumn(icon, 0);
        grid.Children.Add(icon);

        var panel = new StackPanel();
        var head = new TextBlock
        {
            Text = r.Name,
            FontWeight = FontWeights.SemiBold,
            FontSize = 13,
        };
        panel.Children.Add(head);

        var detail = new TextBlock
        {
            Text = r.Detail,
            FontSize = 11.5,
            Foreground = BrushOf("#8494A8"),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 2, 0, 0),
        };
        panel.Children.Add(detail);

        if (r.Ok && !string.IsNullOrEmpty(r.Id))
        {
            string ver = r.Id is "ffmpeg" or "ffprobe" ? DependencyCheck.GetToolVersion(r.Id) : "";
            if (!string.IsNullOrEmpty(ver))
                detail.Text += "   （版本 " + ver + "）";
        }

        Grid.SetColumn(panel, 1);
        grid.Children.Add(panel);
        return grid;
    }

    /// <summary>执行下载安装。</summary>
    private async Task RunInstallAsync()
    {
        _install.IsEnabled = false;
        _install.Content = "正在安装…";
        _bar.Visibility = Visibility.Visible;
        _bar.Value = 0;
        _cts = new CancellationTokenSource();

        var progress = new Progress<DepProgress>(p =>
        {
            _stage.Text = p.Stage;
            if (p.Total > 0)
            {
                _bar.Visibility = Visibility.Visible;
                _bar.Value = p.Percent;
            }
        });

        try
        {
            var res = await DependencyInstaller.InstallFfmpegAsync(progress, _cts.Token)
                                             .ConfigureAwait(true);
            if (res.Ok)
            {
                _stage.Text = "安装完成。";
                _bar.Value = 100;
                Refresh();
                MessageBox.Show(this,
                    "ffmpeg 与 ffprobe 已安装到\n" + DependencyCheck.ToolFfmpegDir +
                    "\n\n现在可以正常下载并合并课程视频了。",
                    "安装成功", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            else
            {
                _stage.Text = "安装失败。";
                MessageBox.Show(this, res.Message, "安装失败",
                    MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        }
        catch (OperationCanceledException)
        {
            _stage.Text = "已取消。";
        }
        catch (Exception ex)
        {
            _stage.Text = "安装出错。";
            MessageBox.Show(this, ex.Message, "安装失败",
                MessageBoxButton.OK, MessageBoxImage.Warning);
        }
        finally
        {
            _install.IsEnabled = true;
            _install.Content = "立即下载安装";
            _bar.Visibility = Visibility.Collapsed;
            Refresh();
        }
    }

    protected override void OnClosed(EventArgs e)
    {
        try { _cts?.Cancel(); } catch { /* ignore */ }
        base.OnClosed(e);
    }
}
