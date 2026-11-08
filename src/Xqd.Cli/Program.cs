using System;
using Xqd.Core;

namespace Xqd.Cli;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        var opt = CliOptions.Parse(args, out int exitCode);
        if (opt == null) return exitCode;          // --help 或参数错误，用法已打印
        var batch = new BatchRunner(opt);
        await batch.RunAsync().ConfigureAwait(false);
        return 0;
    }
}

/// <summary>对照 xqd_batch.py 的 argparse 参数表（并补上 --mode / --platform）。</summary>
public sealed class CliOptions
{
    public string Out = "";
    public int Workers = 2;
    public int SegWorkers = 12;
    public string Tabs = "正式营,体验营";
    public string Quality = "max";
    public string Only = "";
    public string Mode = "api";
    public string Platform = "qianliao";

    public static CliOptions Parse(string[] args, out int exitCode)
    {
        exitCode = 0;
        var o = new CliOptions { Out = Config.EffectiveOutDir(Config.Load()) };
        for (int i = 0; i < args.Length; i++)
        {
            var a = args[i];
            if (a == "--help" || a == "-h") { PrintHelp(); return null; }
            if (i + 1 >= args.Length) continue;       // 该参数没有值，跳过
            switch (a)
            {
                case "--out": o.Out = args[++i]; break;
                case "--workers":
                    if (int.TryParse(args[++i], out var w) && w > 0) o.Workers = w;
                    break;
                case "--seg-workers":
                    if (int.TryParse(args[++i], out var sw) && sw > 0) o.SegWorkers = sw;
                    break;
                case "--tabs": o.Tabs = args[++i]; break;
                case "--quality": o.Quality = args[++i]; break;
                case "--only": o.Only = args[++i]; break;
                case "--mode": o.Mode = args[++i]; break;
                case "--platform": o.Platform = args[++i]; break;
                default: break;                       // 未知参数忽略（不吞下一个 token）
            }
        }
        if (o.Quality != "max" && o.Quality != "720" && o.Quality != "1080")
        {
            Console.Error.WriteLine("无效的 --quality：" + o.Quality + "（可选 max|720|1080）");
            PrintHelp();
            exitCode = 2;
            return null;
        }
        if (o.Mode != "api" && o.Mode != "adb") o.Mode = "api";
        if (string.IsNullOrWhiteSpace(o.Out)) o.Out = Config.EffectiveOutDir(Config.Load());
        return o;
    }

    private static void PrintHelp()
    {
        Console.WriteLine("兴趣岛课程全量下载（CLI 批处理）");
        Console.WriteLine();
        Console.WriteLine("用法:");
        Console.WriteLine("  Xqd.Cli --out <dir> [选项]");
        Console.WriteLine();
        Console.WriteLine("选项:");
        Console.WriteLine("  --out <dir>          输出根目录（默认取 config.json 的 out_dir / 系统下载目录）");
        Console.WriteLine("  --workers <n>        课程级并发数（默认 2）");
        Console.WriteLine("  --seg-workers <n>    每节课分片并发数（默认 12）");
        Console.WriteLine("  --tabs <列表>        逗号分隔的标签，如 正式营,体验营（默认 正式营,体验营）");
        Console.WriteLine("  --quality <q>        画质 max|720|1080（默认 max）");
        Console.WriteLine("  --only <营/课>       只跑名称包含该串的营或课（可选）");
        Console.WriteLine("  --mode <m>           数据源 api|adb（默认 api）");
        Console.WriteLine("  --platform <p>       平台 id（默认 qianliao）");
        Console.WriteLine("  -h, --help           显示本帮助");
        Console.WriteLine();
        Console.WriteLine("示例:");
        Console.WriteLine("  Xqd.Cli --out \"Z:/太极营\" --workers 2 --seg-workers 12 --tabs 正式营,体验营 --quality max");
    }
}
