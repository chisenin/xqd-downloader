using System;
using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Threading;
using Xqd.Core;
using Xqd.Core.Setup;

namespace Xqd.Gui;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += OnUnhandled;
        base.OnStartup(e);

        // ★ v1.6.3：命令行模式 `--install-deps`
        //   无界面静默安装 ffmpeg / ffprobe，供 CI、批量部署、脚本化使用。
        //   用法：xqd-downloader-vX.Y.Z.exe --install-deps
        //   退出码：0=成功（本来就已装也算）、1=失败。
        if (e.Args != null && Array.IndexOf(e.Args, "--install-deps") >= 0)
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = RunInstallDepsAsync();
            return;
        }
    }

    /// <summary>静默安装依赖（命令行模式）。</summary>
    private async System.Threading.Tasks.Task RunInstallDepsAsync()
    {
        int code = 1;
        try
        {
            var results = DependencyCheck.CheckAll();
            if (!DependencyCheck.HasMissingRequired(results))
            {
                Console.WriteLine("依赖已齐全，无需安装：");
                foreach (var r in results) Console.WriteLine("  " + r.Name + " → " + r.Detail);
                code = 0;
            }
            else
            {
                var progress = new Progress<DepProgress>(p =>
                {
                    if (p.Total > 0)
                        Console.WriteLine($"  {p.Percent}%  {p.Stage}  "
                            + $"({p.Done / 1048576.0:F1} / {p.Total / 1048576.0:F1} MB)");
                    else Console.WriteLine("  " + p.Stage);
                });
                var res = await DependencyInstaller.InstallFfmpegAsync(progress).ConfigureAwait(true);
                Console.WriteLine(res.Ok ? "安装成功：" + res.Message : "安装失败：" + res.Message);
                code = res.Ok ? 0 : 1;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("安装出错：" + ex.Message);
            code = 1;
        }
        Shutdown(code);
    }

    private void OnUnhandled(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        // 界面异常不直接崩掉主窗口；尽量留一份诊断文本。
        try
        {
            var dir = Config.ToolDir;
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "gui-error.log"),
                "[" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "] " + e.Exception + Environment.NewLine,
                new UTF8Encoding(false));
        }
        catch { /* ignore */ }
        e.Handled = true;
    }
}
