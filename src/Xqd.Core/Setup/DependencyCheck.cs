using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Xqd.Core.Setup;

/// <summary>
/// 依赖项的检查结果。
/// </summary>
public sealed class DepCheckResult
{
    /// <summary>依赖项的稳定标识（如 "ffmpeg"）。</summary>
    public string Id { get; set; } = "";

    /// <summary>显示名（中文）。</summary>
    public string Name { get; set; } = "";

    /// <summary>是否已就绪。</summary>
    public bool Ok { get; set; }

    /// <summary>缺失时是否致命 —— 致命项缺失会导致下载流程无法完成。</summary>
    public bool Required { get; set; }

    /// <summary>详情：路径、版本、或缺失原因。</summary>
    public string Detail { get; set; } = "";

    /// <summary>是否可由本工具自动下载安装。</summary>
    public bool AutoInstallable { get; set; }
}

/// <summary>
/// ★ v1.6.3：运行环境依赖检查。
///
/// 工具的硬依赖只有两个：
///   ① **ffmpeg / ffprobe** —— 分片转封装（cat → ffmpeg）与成品时长校验（ffprobe）。
///      缺了它，课能下但合并不了 MP4，成品是分片不能播放。
///   ② **.NET 8 桌面运行时** —— WPF 程序的宿主。
///      ⚠️ 缺它时**本工具根本起不来**（framework-dependent 发布），
///         所以程序内检测不到 —— 只能靠「改成自包含发布」根治，
///         或由用户在系统层面安装。见 Setup/DependencyInstaller 的说明。
///
/// MuMu 模拟器只在「首次授权 / 重新授权」时才需要，日常启动不碰它，
/// 因此列为**可选**依赖，缺失时只提示不拦路。
/// </summary>
public static class DependencyCheck
{
    /// <summary>工具自装 ffmpeg 的目录（放在用户目录下，不写 Program Files，免管理员权限）。</summary>
    public static string ToolFfmpegDir => Path.Combine(Config.ToolDir, "ffmpeg", "bin");

    /// <summary>检查全部依赖。返回的列表顺序 = 显示顺序。</summary>
    public static List<DepCheckResult> CheckAll()
    {
        var list = new List<DepCheckResult>();

        // ── ffmpeg（致命）─────────────────────────────────────
        string ff = FindTool("ffmpeg");
        list.Add(new DepCheckResult
        {
            Id = "ffmpeg",
            Name = "ffmpeg（分片转封装）",
            Ok = ff != null,
            Required = true,
            AutoInstallable = true,
            Detail = ff != null ? ff : "未找到 —— 下载的课无法合并为可播放的 MP4",
        });

        // ── ffprobe（致命）────────────────────────────────────
        string fp = FindTool("ffprobe");
        list.Add(new DepCheckResult
        {
            Id = "ffprobe",
            Name = "ffprobe（成品时长校验）",
            Ok = fp != null,
            Required = true,
            AutoInstallable = true,
            Detail = fp != null ? fp : "未找到 —— 无法校验成品时长",
        });

        // ── MuMu 模拟器（可选，仅首次授权需要）────────────────
        string mumu = FindMumu();
        list.Add(new DepCheckResult
        {
            Id = "mumu",
            Name = "MuMu 模拟器（仅首次授权需要）",
            Ok = mumu != null,
            Required = false,
            AutoInstallable = false,
            Detail = mumu != null
                ? mumu
                : "未检测到。日常启动用已保存的授权不受影响；"
                  + "点「重新授权」时才需要它（可从网易官网下载安装）",
        });

        return list;
    }

    /// <summary>是否缺少任何**致命**依赖。</summary>
    public static bool HasMissingRequired(List<DepCheckResult> results) =>
        results != null && results.Any(r => r.Required && !r.Ok);

    /// <summary>
    /// 定位 ffmpeg / ffprobe 可执行文件。
    /// ★ 查找顺序里**新增了「工具自装目录」**（优先级最高）——
    ///   自动安装的 ffmpeg 放在 ~/.xqd_tool/ffmpeg/bin，不写系统 PATH。
    /// </summary>
    public static string FindTool(string name)
    {
        // ① 工具自装目录（本工具自动安装的）
        string selfDir = ToolFfmpegDir;
        string self = Path.Combine(selfDir, name + ".exe");
        if (File.Exists(self)) return self;

        // ② 系统 PATH
        string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var raw in pathEnv.Split(Path.PathSeparator))
        {
            string dir = raw.Trim().Trim('"');
            if (dir.Length == 0) continue;
            try
            {
                string p = Path.Combine(dir, name + ".exe");
                if (File.Exists(p)) return p;
                p = Path.Combine(dir, name);
                if (File.Exists(p)) return p;
            }
            catch { /* 非法 PATH 项跳过 */ }
        }

        // ③ 历史回退目录（用户机器上已有的位置）
        foreach (var dir in new[]
        {
            @"D:\user\chisenin\download\Programs\ffmpeg-8.0.1-essentials_build\bin",
            @"C:\LEL\LEL-Downloader\Source\ffmpeg",
        })
        {
            string p = Path.Combine(dir, name + ".exe");
            if (File.Exists(p)) return p;
        }

        return null;
    }

    /// <summary>定位 MuMuManager.exe（找不到返回 null）。</summary>
    public static string FindMumu()
    {
        foreach (var dir in new[]
        {
            @"D:\Program Files\Netease\MuMu",
            @"C:\Program Files\Netease\MuMu",
            @"D:\Program Files\Netease\MuMu Player",
            @"C:\Program Files\Netease\MuMu Player",
        })
        {
            try
            {
                if (!Directory.Exists(dir)) continue;
                foreach (var rel in new[]
                {
                    @"nx_main\MuMuManager.exe",
                    @"nx_main\MuMuManager.exe",
                    @"shell\MuMuManager.exe",
                })
                {
                    string p = Path.Combine(dir, rel);
                    if (File.Exists(p)) return p;
                    // 兼容 MuMu 12 的 vms 目录结构
                    string alt = Path.Combine(dir, "vms", "MuMuManager.exe");
                    if (File.Exists(alt)) return alt;
                }
            }
            catch { /* 忽略 */ }
        }
        return null;
    }

    /// <summary>取 ffmpeg 版本号（用于界面显示，如 "ffmpeg 6.1.1"）。取不到返回空串。</summary>
    public static string GetToolVersion(string name)
    {
        string exe = FindTool(name);
        if (exe == null) return "";
        try
        {
            var r = Proc.Run(exe, new[] { "-version" }, 15000);
            if (!r.Ok) return "";
            string first = (r.Out ?? "").Split('\n').FirstOrDefault()?.Trim() ?? "";
            // "ffmpeg version 6.1.1 Copyright (c) ..." → 取 "6.1.1"
            var parts = first.Split(' ');
            for (int i = 0; i < parts.Length - 1; i++)
                if (parts[i] == "version") return parts[i + 1];
            return first;
        }
        catch { return ""; }
    }
}
