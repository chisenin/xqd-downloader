using System;
using System.Collections.ObjectModel;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using Xqd.Core.Setup;

namespace Xqd.Avalonia.Views;

/// <summary>依赖项一行。</summary>
public sealed class DepVm
{
    public string Name { get; set; } = "";
    public string Detail { get; set; } = "";
    public bool Ok { get; set; }
    public bool Required { get; set; }
    public string StatusText => Ok ? "就绪" : (Required ? "缺失（必须）" : "缺失（可选）");
    public string StatusColor => Ok ? "#2E7D4F" : (Required ? "#B33A3A" : "#B26A00");
    public string DotColor => Ok ? "#4E9A3E" : (Required ? "#C0392B" : "#D19A3E");
}

public partial class EnvCheckWindow : Window
{
    /// <summary>本次窗口里是否装过 / 改过工具位置（关窗后主窗据此重扫）。</summary>
    public bool Changed { get; private set; }

    private readonly ObservableCollection<DepVm> _items = new();

    public EnvCheckWindow()
    {
        InitializeComponent();
        LstDeps.ItemsSource = _items;
        RefreshList();
    }

    private void RefreshList()
    {
        _items.Clear();
        foreach (var d in DependencyCheck.CheckAll())
        {
            _items.Add(new DepVm
            {
                Name = d.Name,
                Detail = d.Detail,
                Ok = d.Ok,
                Required = d.Required,
            });
        }

        // 自动安装按钮只在 ffmpeg/ffprobe 缺失时可用
        bool missingFf = _items.Any(i => !i.Ok && (i.Name.StartsWith("ffmpeg") || i.Name.StartsWith("ffprobe")));
        BtnInstall.IsEnabled = missingFf;
        BtnInstall.Content = missingFf ? "自动安装 ffmpeg" : "ffmpeg 已就绪";

        string mumu = DependencyCheck.FindMumu() ?? "";
        BtnPickMumu.Content = mumu.Length > 0 ? "更换 MuMu 位置" : "指定 MuMuManager…";
    }

    private void BtnRefresh_Click(object sender, RoutedEventArgs e) => RefreshList();

    private async void BtnInstall_Click(object sender, RoutedEventArgs e)
    {
        BtnInstall.IsEnabled = false;
        InstallPanel.IsVisible = true;
        BarInstall.Value = 0;
        LblInstall.Text = "正在连接国内镜像…";

        var progress = new Progress<DepProgress>(p => Dispatcher.UIThread.Post(() =>
        {
            if (p.Total > 0)
                BarInstall.Value = p.Percent;
            LblInstall.Text = $"[{p.SourceName}] {p.Stage} {p.Percent}%";
        }));

        try
        {
            var r = await DependencyInstaller.InstallFfmpegAsync(progress);
            LblInstall.Text = r.Message;
            BarInstall.Value = r.Ok ? 100 : BarInstall.Value;
            if (r.Ok)
            {
                Changed = true;
                LblHint.Text = "安装完成：" + r.Ffmpeg;
            }
            else
            {
                LblHint.Text = "自动安装失败 —— 可手动下载 ffmpeg 后，把解压出来的 bin 目录告诉我"
                             + "（或设环境变量 XQD_FFMPEG_DIR）。";
            }
        }
        catch (Exception ex)
        {
            LblInstall.Text = "安装失败：" + ex.Message;
        }
        finally
        {
            RefreshList();
            BtnInstall.IsEnabled = true;
        }
    }

    private async void BtnPickMumu_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "选择 MuMuManager.exe（在 MuMu 安装目录的 nx_main 里）",
                AllowMultiple = false,
                FileTypeFilter = new[]
                {
                    new FilePickerFileType("MuMuManager.exe")
                    {
                        Patterns = new[] { "MuMuManager.exe" },
                    },
                },
            });
            if (files == null || files.Count == 0) return;
            string path = files[0].TryGetLocalPath() ?? "";
            if (path.Length == 0) return;
            if (!ToolLocator.RememberMumuManager(path))
            {
                LblHint.Text = "这个文件不是 MuMuManager.exe：" + path;
                return;
            }
            Changed = true;
            LblHint.Text = "已记住 MuMu 位置：" + path;
            RefreshList();
        }
        catch (Exception ex)
        {
            LblHint.Text = "选择失败：" + ex.Message;
        }
    }

    private void BtnClose_Click(object sender, RoutedEventArgs e) => Close();
}
