using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Xqd.Core;

namespace Xqd.Gui.Controls;

/// <summary>
/// 「使用说明与关于」合并对话框（点顶栏品牌区任意位置弹出）。
/// 上半是完整六步操作流程，往下滚是版本、参考与引用的开源项目、特别声明。
/// 纯代码构建，避免额外 XAML / 外部 HTML 渲染依赖。
/// </summary>
public sealed class HelpAboutWindow : Window
{
    public HelpAboutWindow(Window owner)
    {
        Owner = owner;
        Title = "使用说明与关于";
        Width = 700;
        Height = 640;
        MinWidth = 480;
        MinHeight = 380;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F4F6FA"));
        FontFamily = new FontFamily("Microsoft YaHei UI, Microsoft YaHei, Segoe UI, sans-serif");

        var root = new Grid { Margin = new Thickness(14, 12, 14, 12) };
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        var scroll = new ScrollViewer
        {
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            Padding = new Thickness(8),
            Background = Brushes.White,
        };
        var panel = new StackPanel { Margin = new Thickness(4) };
        scroll.Content = panel;

        // ── 上半：使用说明（六步） ──
        Heading(panel, "使用说明");
        Body(panel, "1. 授权（平时不用开模拟器）");
        Body(panel, "顶栏显示「授权：…」。平时启动工具直接使用本机保存的授权，不会拉起 MuMu 模拟器。只有首次使用（本机还没保存过授权），或点顶栏「重新授权」时，才会拉起 MuMu 与安卓设备读取登录态，读完自动关闭模拟器并把新凭据保存到本机。凭据只存在 %USERPROFILE%\\.xqd_tool\\cookie.txt（也可用环境变量 XQD_COOKIE 覆盖）。");
        Body(panel, "2. 选择营");
        Body(panel, "左栏「营列表」列出你已订阅的营，用顶部标签切换「全部 / 正式营 / 体验营 / 轻课」。点营名前面的方框可勾选多个营，表头「全选」一次全勾；勾选的营，其课程会合并进右侧同一张课程列表，每节课仍存到自己营的同名文件夹里。多个营名用「·」分隔并向左循环滚动（鼠标悬停看完整名单）。一个都不勾时，仍显示当前高亮的那个营。");
        Body(panel, "3. 勾选课程");
        Body(panel, "「标题前缀」是该课在原营课表里的序号 —— 多营合并也不会重新编号，和成品文件名的前缀完全对应；「标题后缀」列是成品文件名里的日期。「进度」列显示实际下载进度：已下完 100%，没下完按下载历史 / 可续传分片缓存显示百分比，重新载入课表也不会变空。点表头左侧方框可全选，也可双击某行直接下载该课。已完整下载过的课会自动标记并跳过；残缺文件会被清除并用规范名重下。");
        Body(panel, "4. 选择保存目录");
        Body(panel, "顶栏「下载目录」指定保存位置。首次使用默认指向 Windows 的「下载」文件夹（跟随系统的文档重定向）；手动改过之后会一直沿用最后一次修改的目录。改动方式：直接改输入框后按回车，或点「浏览…」选择。");
        Body(panel, "5. 开始下载");
        Body(panel, "点「下载选中」批量下载。「下载管理」表实时显示状态、大小（已下/总量）、速度、剩余时间、进度；状态词在「课名后 / 管理表状态列 / 运行日志」三处一一对应。一节进入「封装中」后网络即被释放，队列里的下一节会立刻开跑（最多 3 节下载 + 2 节封装）。输出结构：<营名>\\<序号>.<课名>.<YYYY.MM.DD>.mp4，音频课保留原始容器。");
        Body(panel, "6. 暂停 / 失败重试 / 管理");
        Body(panel, "点橙色「暂停」停住全部下载（已下好的分片保留，点「继续」从断点接着下）；失败的课会自动重新勾选，再点「下载选中」即可重下。「清除列表」只清任务表与历史记录、不动文件；「删除文件」把对应成品移到下载目录下的 _已删除 子目录。关掉工具再打开，下载列表与进度都还在（%USERPROFILE%\\.xqd_tool\\history.json 与 parts\\）。");

        Separator(panel);

        // ── 下半：关于 / 开源声明 / 特别声明 ──
        Heading(panel, "关于本工具");
        Body(panel, States.AppTitle + "  v" + States.AppVersion);
        Body(panel, "把「兴趣岛」App 里你已付费订阅的课程视频批量导出为通用 MP4，便于在教学大屏上直接播放。本工具独立编写：业务接口契约来自官方前端明文，下载内核（分片并行、断点续下、拼接转封装）自行实现。");

        Heading(panel, "参考与引用的开源项目");
        Body(panel, "学无止下载器 — MIT License — https://github.com/Xue-Wu-Zhi/xuewuzhi-downloader（参考其公开的平台目录与文档，了解各教学平台的接口形态与常见加密方式）。");
        Body(panel, "Qt → WPF — 原版（Python）基于 PySide6 / Qt for Python（LGPL-3.0）构建界面；本 C# 移植版改用 .NET 8 WPF，仅用框架基础类库，界面按同一套扁平风格用 Styles / Brushes / ControlTemplate 复刻。");
        Body(panel, "FFmpeg — LGPL-2.1+ / GPL（视构建而定）：用于把 HLS 分片拼接转封装为 MP4，并用 ffprobe 校验成品时长。");
        Body(panel, "pycryptodome — BSD-2-Clause / Public Domain：网易云课堂（163）视频地址 AES 解密内核。");

        Heading(panel, "特别声明");
        Body(panel, "在摸清兴趣岛与网易云课堂的接口细节时，曾分析学无止下载器官方 Windows 客户端（V1.5.0 / V2.19.70）的行为。本仓库中 _lel/core/netease_mooc.py（网易课堂 163 视频地址解密）系依据其 V1.5.0 Source/core 的逻辑独立复现；_lel/login/、_lel/v2/ 为分析过程的记录。");
        Body(panel, "上述部分不属于 Xue-Wu-Zhi/xuewuzhi-downloader 仓库的 MIT 授权范围（该仓库仅公开文档与 Python 离线骨架，官方客户端不在其源码授权内）。本工具不含其客户端代码，仅用于个人学习与本地教学演示。");
        Body(panel, "使用者请遵守课程提供方的授权要求，只处理自己有权访问与保存的内容。本工具不提供、也不鼓励用于未购内容的批量获取。");

        Grid.SetRow(scroll, 0);
        root.Children.Add(scroll);

        var btnClose = new Button
        {
            Content = "关闭",
            Width = 96,
            Height = 30,
            Margin = new Thickness(0, 10, 0, 0),
            HorizontalAlignment = HorizontalAlignment.Right,
            Style = (Style)Application.Current.Resources["ModernButtonStyle"],
            IsDefault = true,
        };
        btnClose.Click += (_, _) => Close();
        Grid.SetRow(btnClose, 1);
        root.Children.Add(btnClose);

        Content = root;
    }

    private static void Heading(StackPanel p, string text) =>
        p.Children.Add(new TextBlock
        {
            Text = text,
            FontSize = 16,
            FontWeight = FontWeights.SemiBold,
            Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2F5D8F")),
            Margin = new Thickness(0, 14, 0, 6),
        });

    private static void Body(StackPanel p, string text) =>
        p.Children.Add(new TextBlock
        {
            Text = text,
            FontSize = 13,
            TextWrapping = TextWrapping.Wrap,
            Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2B3445")),
            Margin = new Thickness(0, 3, 0, 3),
        });

    private static void Separator(StackPanel p) =>
        p.Children.Add(new Border
        {
            Height = 1,
            Margin = new Thickness(0, 14, 0, 4),
            Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#D3DAE6")),
        });
}
