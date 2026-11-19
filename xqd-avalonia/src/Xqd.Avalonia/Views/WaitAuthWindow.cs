using System;
using System.Threading;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Xqd.Core.Auth;

namespace Xqd.Avalonia.Views;

/// <summary>
/// 等待授权小窗（对应 hgvd 的 WaitAuthWindow）。
///
/// 场景：模拟器开着一台空的、或 App 还没登录 —— 与其让用户对着「App 未登录」
/// 反复点重试，不如弹这个置顶窗：每 2 秒扫一次运行中的实例，读到可用登录态就
/// 自动关窗并返回实例号，主窗随即重跑一次授权。
///
/// 结果：<c>ShowDialog&lt;int&gt;</c> 返回实例号；<c>-1</c> = 超时/取消。
/// </summary>
public sealed class WaitAuthWindow : Window
{
    private readonly TextBlock _status;
    private readonly TextBlock _timer;
    private readonly TextBox _log;
    private readonly CancellationTokenSource _cts = new();
    private readonly DateTime _started = DateTime.UtcNow;
    private readonly int _timeoutSec;
    private int _result = -1;

    public WaitAuthWindow(int timeoutSec = 180)
    {
        _timeoutSec = Math.Max(10, timeoutSec);

        Title = "等待授权";
        Width = 520;
        Height = 360;
        CanResize = false;
        Topmost = true;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SystemDecorations = SystemDecorations.BorderOnly;
        Background = new SolidColorBrush(Color.Parse("#F4F6FA"));
        FontFamily = new FontFamily("Microsoft YaHei UI, Segoe UI");

        var root = new Grid
        {
            RowDefinitions = new RowDefinitions("Auto,Auto,*,Auto"),
            Margin = new Thickness(20, 18, 20, 14),
        };

        var head = new StackPanel { Spacing = 6 };
        head.Children.Add(new TextBlock
        {
            Text = "等待「兴趣岛」登录态",
            FontSize = 16,
            FontWeight = FontWeight.SemiBold,
            Foreground = new SolidColorBrush(Color.Parse("#1F2937")),
        });
        head.Children.Add(new TextBlock
        {
            Text = "请打开 MuMu → 启动装了「兴趣岛」的安卓机 → 在 App 里登录。"
                 + "读到登录态会自动继续，无需手动点重试。",
            FontSize = 12,
            TextWrapping = TextWrapping.Wrap,
            Foreground = new SolidColorBrush(Color.Parse("#5A6675")),
        });
        root.Children.Add(head);
        Grid.SetRow(head, 0);

        _status = new TextBlock
        {
            Text = "正在扫描实例…",
            FontSize = 12.5,
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 12, 0, 8),
            Foreground = new SolidColorBrush(Color.Parse("#2F6FB2")),
        };
        root.Children.Add(_status);
        Grid.SetRow(_status, 1);

        _log = new TextBox
        {
            IsReadOnly = true,
            AcceptsReturn = true,
            TextWrapping = TextWrapping.Wrap,
            FontSize = 11.5,
            Background = Brushes.White,
            BorderBrush = new SolidColorBrush(Color.Parse("#DCE1E8")),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(8),
            Padding = new Thickness(10, 8),
            MinHeight = 120,
        };
        ScrollViewer.SetVerticalScrollBarVisibility(_log, ScrollBarVisibility.Auto);
        root.Children.Add(_log);
        Grid.SetRow(_log, 2);

        var footer = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Spacing = 10,
            Margin = new Thickness(0, 10, 0, 0),
        };
        _timer = new TextBlock
        {
            Text = "",
            FontSize = 12,
            VerticalAlignment = VerticalAlignment.Center,
            Foreground = new SolidColorBrush(Color.Parse("#5A6675")),
        };
        var btnCancel = new Button { Content = "取消等待", MinWidth = 96 };
        btnCancel.Click += (_, _) => { _cts.Cancel(); Close(-1); };
        footer.Children.Add(_timer);
        footer.Children.Add(btnCancel);
        root.Children.Add(footer);
        Grid.SetRow(footer, 3);

        Content = root;

        Opened += async (_, _) => await RunAsync();
        Closed += (_, _) => { try { _cts.Cancel(); } catch { } };
    }

    /// <summary>弹窗返回的实例号；-1 = 没等到。</summary>
    public int ResultIndex => _result;

    private void AddLog(string msg)
    {
        string line = $"[{DateTime.Now:HH:mm:ss}] {msg}";
        _log.Text = string.IsNullOrEmpty(_log.Text) ? line : _log.Text + "\n" + line;
        _log.CaretIndex = _log.Text?.Length ?? 0;
    }

    private async Task RunAsync()
    {
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        timer.Tick += (_, _) =>
        {
            int elapsed = (int)(DateTime.UtcNow - _started).TotalSeconds;
            _timer.Text = $"已等待 {elapsed}s / 最长 {_timeoutSec}s   ";
            if (elapsed >= _timeoutSec) timer.Stop();
        };
        timer.Start();

        try
        {
            var r = await MumuAuth.WaitForLoginAsync(
                _timeoutSec,
                msg => Dispatcher.UIThread.Post(() =>
                {
                    _status.Text = msg;
                    AddLog(msg);
                }),
                _cts.Token);

            _result = r.Index;
            _status.Text = r.Message;
            AddLog(r.Message);

            if (r.Ok)
            {
                // 稍等一下让用户看到「已登录」，再自动关窗继续
                await Task.Delay(600);
                Close(_result);
            }
            else
            {
                await Task.Delay(200);
                Close(-1);
            }
        }
        catch (OperationCanceledException)
        {
            Close(-1);
        }
        catch (Exception e)
        {
            AddLog("等待失败：" + e.Message);
            _status.Text = "等待失败：" + e.Message;
            await Task.Delay(300);
            Close(-1);
        }
        finally
        {
            timer.Stop();
        }
    }
}
