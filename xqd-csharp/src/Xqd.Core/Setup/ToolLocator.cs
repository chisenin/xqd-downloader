using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Xqd.Core.Setup;

/// <summary>
/// 外部工具定位 —— **本机化路径的唯一克星**。
///
/// 目标：换一台机器，只要装了 MuMu / ffmpeg（或让本工具自动装过），
/// 就一定能找到；一个硬编码盘符都不留。
///
/// 查找顺序（每类工具都一样：用户显式指定 &gt; 本工具自装 &gt; 环境变量 &gt; 常规安装位置 &gt; PATH）：
///   ① 用户在界面里点选过的路径（~/.xqd_tool/tools.json 记住）
///   ② 本工具自装目录（~/.xqd_tool/ffmpeg/bin）
///   ③ 环境变量（XQD_FFMPEG_DIR / XQD_MUMU_MANAGER / XQD_ADB）
///   ④ 常规安装位置：Program Files、各盘根目录的 Netease\MuMu 等
///   ⑤ PATH
/// </summary>
public static class ToolLocator
{
    public static string ToolsFile => Path.Combine(Config.ToolDir, "tools.json");

    private static JsonDocument _doc;
    private static readonly object Gate = new();

    private static JsonDocument Overrides()
    {
        lock (Gate)
        {
            if (_doc != null) return _doc;
            try
            {
                if (File.Exists(ToolsFile))
                    _doc = JsonDocument.Parse(File.ReadAllText(ToolsFile, Encoding.UTF8));
            }
            catch { _doc = null; }
            if (_doc == null) _doc = JsonDocument.Parse("{}");
            return _doc;
        }
    }

    private static string GetOverride(string key)
    {
        try
        {
            var root = Overrides().RootElement;
            if (root.ValueKind == JsonValueKind.Object &&
                root.TryGetProperty(key, out var v) &&
                v.ValueKind == JsonValueKind.String)
                return v.GetString() ?? "";
        }
        catch { /* 配置坏了就当没配 */ }
        return "";
    }

    private static void SetOverride(string key, string value)
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        try
        {
            var root = Overrides().RootElement;
            if (root.ValueKind == JsonValueKind.Object)
                foreach (var p in root.EnumerateObject())
                    if (p.Value.ValueKind == JsonValueKind.String)
                        map[p.Name] = p.Value.GetString() ?? "";
        }
        catch { }
        if (string.IsNullOrWhiteSpace(value)) map.Remove(key);
        else map[key] = value;

        try
        {
            var dir = Path.GetDirectoryName(ToolsFile);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(ToolsFile,
                JsonSerializer.Serialize(map, new JsonSerializerOptions { WriteIndented = true }),
                new UTF8Encoding(false));
            lock (Gate)
            {
                _doc?.Dispose();
                _doc = null;
            }
        }
        catch { /* 记不住不影响本次使用 */ }
    }

    // ══════════════════════ ffmpeg / ffprobe ══════════════════════

    /// <summary>本工具自装 ffmpeg 的目录（不写系统 PATH，免管理员权限）。</summary>
    public static string FfmpegSelfDir => Path.Combine(Config.ToolDir, "ffmpeg", "bin");

    /// <summary>用户点选过的 ffmpeg 目录（记在 tools.json 里）。</summary>
    public static string FfmpegExtraDir => GetOverride("ffmpeg_dir");

    /// <summary>记住用户选的 ffmpeg 目录（传空串 = 清除）。</summary>
    public static void RememberFfmpegDir(string dir) => SetOverride("ffmpeg_dir", dir);

    /// <summary>
    /// 定位 ffmpeg / ffprobe。找不到返回 null（调用方决定是否抛异常）。
    /// </summary>
    public static string FindTool(string name)
    {
        var exeNames = OperatingSystem.IsWindows()
            ? new[] { name + ".exe" }
            : new[] { name };

        // ① 用户显式指定 / ② 自装目录
        foreach (var dir in new[] { FfmpegExtraDir, FfmpegSelfDir })
        {
            if (string.IsNullOrWhiteSpace(dir)) continue;
            foreach (var n in exeNames)
            {
                var p = Path.Combine(dir, n);
                if (File.Exists(p)) return p;
            }
        }

        // ③ 环境变量
        string envDir = Environment.GetEnvironmentVariable("XQD_FFMPEG_DIR") ?? "";
        if (!string.IsNullOrWhiteSpace(envDir))
            foreach (var n in exeNames)
            {
                var p = Path.Combine(envDir.Trim().Trim('"'), n);
                if (File.Exists(p)) return p;
            }

        // ④ PATH
        foreach (var p in PathCandidates(name))
            if (File.Exists(p)) return p;

        return null;
    }

    /// <summary>PATH 里逐个目录找可执行文件（Windows 兼容 exe 后缀）。</summary>
    public static IEnumerable<string> PathCandidates(string name)
    {
        string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
        var exts = OperatingSystem.IsWindows()
            ? new[] { name + ".exe", name }
            : new[] { name, name + ".exe" };
        foreach (var raw in pathEnv.Split(Path.PathSeparator))
        {
            string dir = (raw ?? "").Trim().Trim('"');
            if (dir.Length == 0) continue;
            foreach (var n in exts)
            {
                string p;
                try { p = Path.Combine(dir, n); } catch { continue; }
                yield return p;
            }
        }
    }

    // ══════════════════════ MuMu 模拟器 ══════════════════════

    /// <summary>用户点选过的 MuMuManager.exe（记在 tools.json 里）。</summary>
    public static string MumuManagerOverride => GetOverride("mumu_manager");

    /// <summary>记住 MuMuManager.exe 的位置（传空串 = 清除）。</summary>
    public static bool RememberMumuManager(string path)
    {
        if (string.IsNullOrWhiteSpace(path)) { SetOverride("mumu_manager", ""); return false; }
        if (!File.Exists(path)) return false;
        SetOverride("mumu_manager", Path.GetFullPath(path));
        return true;
    }

    /// <summary>
    /// MuMu 安装根目录候选 —— **按盘符枚举**，不写死 D:。
    /// 覆盖 Program Files / Program Files (x86) / 用户级安装 / 各盘直接安装。
    /// </summary>
    private static IEnumerable<string> MumuRoots()
    {
        // ① 用户/环境显式指定的根目录
        string envRoot = Environment.GetEnvironmentVariable("XQD_MUMU_HOME") ?? "";
        if (!string.IsNullOrWhiteSpace(envRoot)) yield return envRoot.Trim().Trim('"');

        // ② 用户点选过的 MuMuManager 所在目录的上一级（nx_main 的父目录）
        string chosen = MumuManagerOverride;
        if (!string.IsNullOrWhiteSpace(chosen))
        {
            var dir = Path.GetDirectoryName(chosen);
            if (!string.IsNullOrEmpty(dir))
            {
                yield return dir;                                  // nx_main
                var up = Path.GetDirectoryName(dir);
                if (!string.IsNullOrEmpty(up)) yield return up;     // MuMu 根
            }
        }

        // ③ 常规安装位置（按实际存在的盘符枚举）
        //   ★ 实测：MuMu 12 的默认安装目录是 `Netease\MuMuPlayer-12.0`，
        //     不带版本号后缀的 "MuMu" 根本不存在 —— 旧列表漏了它，机器上装了也判成没装。
        var names = new[]
        {
            "MuMu", "MuMu Player", "MuMuPlayer",
            "MuMuPlayer-12.0", "MuMu Player 12",
            "Netease\\MuMu", "Netease\\MuMu Player",
            "Netease\\MuMuPlayer", "Netease\\MuMuPlayer-12.0",
            "Netease\\MuMu Player 12",
        };
        var envDirs = new List<string>();
        foreach (var v in new[] { "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432" })
        {
            var d = Environment.GetEnvironmentVariable(v);
            if (!string.IsNullOrWhiteSpace(d)) envDirs.Add(d);
        }
        envDirs.Add(Path.Combine(Config.HomeDir, "AppData", "Local", "Netease"));
        envDirs.Add(Path.Combine(Config.HomeDir, "AppData", "Local", "Programs"));

        foreach (var baseDir in envDirs.Where(Directory.Exists))
            foreach (var n in names)
                yield return Path.Combine(baseDir, n);

        // 各盘根目录（D:\Netease\MuMu、D:\Program Files\Netease\MuMu 之类）
        foreach (var drive in FixedDrives())
        {
            yield return Path.Combine(drive, "Netease", "MuMu");
            yield return Path.Combine(drive, "Netease", "MuMu Player");
            yield return Path.Combine(drive, "Netease", "MuMuPlayer-12.0");
            yield return Path.Combine(drive, "Program Files", "Netease", "MuMu");
            yield return Path.Combine(drive, "Program Files", "Netease", "MuMu Player");
            yield return Path.Combine(drive, "Program Files", "Netease", "MuMuPlayer-12.0");
            yield return Path.Combine(drive, "Program Files (x86)", "Netease", "MuMu");
            yield return Path.Combine(drive, "Program Files (x86)", "Netease", "MuMuPlayer-12.0");
            yield return Path.Combine(drive, "MuMu");
            yield return Path.Combine(drive, "MuMu Player");
            yield return Path.Combine(drive, "MuMuPlayer-12.0");
        }
    }

    private static IEnumerable<string> FixedDrives()
    {
        if (!OperatingSystem.IsWindows()) yield break;
        DriveInfo[] drives;
        try { drives = DriveInfo.GetDrives(); } catch { yield break; }
        foreach (var d in drives)
        {
            bool ok;
            try { ok = d.IsReady && d.DriveType == DriveType.Fixed; } catch { ok = false; }
            if (ok) yield return d.RootDirectory.FullName;
        }
    }

    /// <summary>
    /// 找 MuMuManager.exe（找不到返回 null，不抛异常 —— 让界面决定怎么引导）。
    /// 顺序：点选记录 → 环境变量 → 常规安装位置（深搜限 2 层）→ PATH。
    /// </summary>
    public static string FindMumuManager()
    {
        // ① 点选过且仍然存在
        string chosen = MumuManagerOverride;
        if (!string.IsNullOrWhiteSpace(chosen) && File.Exists(chosen)) return chosen;

        // ② 环境变量
        string env = Environment.GetEnvironmentVariable("XQD_MUMU_MANAGER") ?? "";
        if (!string.IsNullOrWhiteSpace(env) && File.Exists(env)) return env;

        // ③ 常规位置 + 深搜
        foreach (var root in MumuRoots())
        {
            if (string.IsNullOrWhiteSpace(root) || !Directory.Exists(root)) continue;
            foreach (var rel in new[]
                     {
                         Path.Combine("nx_main", "MuMuManager.exe"),
                         "MuMuManager.exe",
                         Path.Combine("nemu", "MuMuManager.exe"),
                         Path.Combine("shell", "MuMuManager.exe"),
                         Path.Combine("vms", "MuMuManager.exe"),
                     })
            {
                var p = Path.Combine(root, rel);
                if (File.Exists(p)) return p;
            }
            var found = SearchFile(root, "MuMuManager.exe", 0);
            if (found != null) return found;
        }

        // ④ PATH
        foreach (var p in PathCandidates("MuMuManager"))
            if (File.Exists(p)) return Path.GetFullPath(p);

        return null;
    }

    /// <summary>限深搜索（避免在各盘乱爬）。</summary>
    private static string SearchFile(string dir, string fileName, int depth)
    {
        if (depth > 2) return null;
        try
        {
            var direct = Path.Combine(dir, fileName);
            if (File.Exists(direct)) return direct;
            foreach (var sub in Directory.EnumerateDirectories(dir))
            {
                var found = SearchFile(sub, fileName, depth + 1);
                if (found != null) return found;
            }
        }
        catch { /* 无权限 / 设备目录跳过 */ }
        return null;
    }

    // ══════════════════════ ADB（旧路径） ══════════════════════

    /// <summary>
    /// 找 adb.exe：点选记录 → 环境变量 XQD_ADB → MuMu 自带（nx_main / 安装根）→ PATH。
    /// </summary>
    public static string FindAdb()
    {
        string chosen = GetOverride("adb");
        if (!string.IsNullOrWhiteSpace(chosen) && File.Exists(chosen)) return chosen;

        string env = Environment.GetEnvironmentVariable("XQD_ADB") ?? "";
        if (!string.IsNullOrWhiteSpace(env) && File.Exists(env)) return env;

        string mumu = FindMumuManager();
        if (!string.IsNullOrWhiteSpace(mumu))
        {
            var dir = Path.GetDirectoryName(mumu) ?? "";
            var candidates = new[]
            {
                Path.Combine(dir, "adb.exe"),
                Path.Combine(dir, "adb_server.exe"),
            };
            foreach (var p in candidates)
                if (File.Exists(p)) return p;

            var root = Path.GetDirectoryName(dir) ?? "";
            foreach (var p in new[]
                     {
                         Path.Combine(root, "adb.exe"),
                         Path.Combine(dir, "..", "adb.exe"),
                     })
            {
                try { if (File.Exists(p)) return Path.GetFullPath(p); } catch { }
            }
        }

        foreach (var p in PathCandidates("adb"))
            if (File.Exists(p)) return Path.GetFullPath(p);

        return null;
    }

    /// <summary>
    /// 解析 ADB 设备地址：环境变量 XQD_ADB_DEVICE 优先，否则用 adb devices 取第一台在线设备。
    /// 找不到返回空串（ADB 是旧路径，API 模式不依赖它）。
    /// </summary>
    public static string ResolveAdbDevice(string adbExe = null)
    {
        string env = Environment.GetEnvironmentVariable("XQD_ADB_DEVICE") ?? "";
        if (!string.IsNullOrWhiteSpace(env)) return env.Trim();

        adbExe ??= FindAdb();
        if (string.IsNullOrWhiteSpace(adbExe) || !File.Exists(adbExe)) return "";

        try
        {
            var r = Proc.Run(adbExe, new[] { "devices" }, 15000);
            if (!r.Ok) return "";
            foreach (var raw in (r.Out ?? "").Split('\n'))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("List of devices")) continue;
                var parts = line.Split('\t', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length >= 2 && parts[1].Trim() == "device") return parts[0].Trim();
            }
        }
        catch { /* adb 不在 / 无设备 */ }
        return "";
    }
}
