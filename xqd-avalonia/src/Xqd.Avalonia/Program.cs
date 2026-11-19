using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Avalonia;
using Xqd.Core;
using Xqd.Core.Setup;

namespace Xqd.Avalonia;

internal static class Program
{
    [STAThread]
    public static int Main(string[] args)
    {
        // ── 无界面模式（CI / 运维用）：不启动 Avalonia，纯控制台 ──
        //   --install-deps   自动装 ffmpeg/ffprobe 后退出
        //   --check          打印依赖与配置体检结果
        //   --authcheck      打印 MuMu 路径 + 各实例授权状态（换机器排障用）
        //   --version        打印版本
        if (args.Length > 0)
        {
            var cmd = args[0];
            if (cmd == "--install-deps")
            {
                bool ok = RunInstallDeps().GetAwaiter().GetResult();
                return ok ? 0 : 1;
            }
            if (cmd == "--check")
            {
                RunCheck();
                return 0;
            }
            if (cmd == "--authcheck")
            {
                return RunAuthCheck();
            }
            if (cmd == "--version")
            {
                Console.WriteLine(AppInfo.Version);
                return 0;
            }
        }

        BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
        return 0;
    }

    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .WithInterFont()
            .LogToTrace();

    private static async Task<bool> RunInstallDeps()
    {
        Console.WriteLine("下载 ffmpeg / ffprobe 到 " + DependencyCheck.ToolFfmpegDir);
        var progress = new Progress<DepProgress>(p =>
        {
            Console.WriteLine($"  [{p.SourceName}] {p.Stage} {p.Percent}%");
        });
        var r = await DependencyInstaller.InstallFfmpegAsync(progress).ConfigureAwait(false);
        Console.WriteLine(r.Message);
        return r.Ok;
    }

    private static void RunCheck()
    {
        Console.WriteLine("xqd-downloader " + AppInfo.Version);
        Console.WriteLine("配置目录：" + Config.ToolDir);
        Console.WriteLine("下载目录：" + Config.EffectiveOutDir(Config.Load()));
        Console.WriteLine();
        foreach (var d in DependencyCheck.CheckAll())
            Console.WriteLine($"  {(d.Ok ? "[✓]" : "[✗]")} {d.Name}：{d.Detail}");
    }

    /// <summary>
    /// --authcheck：换机器「拿不到授权」时的自证入口。
    /// 打印 MuMuManager 实际路径、每台实例的启动与登录状态、最终会选哪台。
    /// </summary>
    private static int RunAuthCheck()
    {
        Console.WriteLine("xqd-downloader " + AppInfo.Version + " · 授权诊断");
        try
        {
            var text = Xqd.Core.Auth.MumuAuth.DiagnoseAsync().GetAwaiter().GetResult();
            Console.WriteLine(text);
            return 0;
        }
        catch (Exception e)
        {
            Console.WriteLine("诊断失败：" + e.Message);
            return 1;
        }
    }
}
