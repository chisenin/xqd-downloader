using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using Microsoft.Win32;

namespace Xqd.Core;

/// <summary>持久化配置（config.json）。out_dir 是「用户最后用的下载目录」的唯一事实来源。</summary>
public sealed class AppConfig
{
    public string out_dir { get; set; } = "";
    public bool auto_launch { get; set; } = true;
    public bool auto_close { get; set; } = true;
    public string platform { get; set; } = "qianliao";
    public string quality { get; set; } = "max";
    public string mode { get; set; } = "api";
    public int workers { get; set; } = 2;
    public int seg_workers { get; set; } = 12;
}

public static class Config
{
    private static readonly JsonSerializerOptions JsonOpt = new()
    {
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        PropertyNameCaseInsensitive = true,
    };

    // 测试隔离：XQD_TEST_HOME 只影响配置 / 历史 / 分片缓存，**不影响凭据读取**。
    public static string TestHome => Environment.GetEnvironmentVariable("XQD_TEST_HOME") ?? "";

    public static string HomeDir =>
        Environment.GetEnvironmentVariable("USERPROFILE")
        ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile)
        ?? ".";

    public static string ToolDir => string.IsNullOrEmpty(TestHome)
        ? Path.Combine(HomeDir, ".xqd_tool")
        : TestHome;

    public static string ConfigFile => Path.Combine(ToolDir, "config.json");
    public static string HistoryFile => Path.Combine(ToolDir, "history.json");
    public static string PartsDir => Path.Combine(ToolDir, "parts");

    /// <summary>凭据文件固定在真实用户目录下，不受 XQD_TEST_HOME 影响。</summary>
    public static string CredFile => Path.Combine(HomeDir, ".xqd_tool", "cookie.txt");

    private static readonly HashSet<string> LegacyOutDirs = new(StringComparer.OrdinalIgnoreCase)
    {
        @"Z:\太极营", "Z:/太极营"
    };

    public static AppConfig Load(string path = null)
    {
        try
        {
            var p = path ?? ConfigFile;
            if (!File.Exists(p)) return new AppConfig();
            return JsonSerializer.Deserialize<AppConfig>(File.ReadAllText(p, Encoding.UTF8), JsonOpt)
                   ?? new AppConfig();
        }
        catch { return new AppConfig(); }
    }

    public static void Save(AppConfig cfg, string path = null)
    {
        try
        {
            var p = path ?? ConfigFile;
            var dir = Path.GetDirectoryName(p);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(p, JsonSerializer.Serialize(cfg, JsonOpt), new UTF8Encoding(false));
        }
        catch (Exception e) { Console.Error.WriteLine("保存配置失败：" + e.Message); }
    }

    /// <summary>
    /// Windows「下载」文件夹：必须读注册表 Known Folder GUID，
    /// 不能用 USERPROFILE + "Downloads"（本机被重定向到 D:\user\chisenin\download）。
    /// </summary>
    public static string WindowsDownloadDir()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(
                @"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders");
            var val = key?.GetValue("{374DE290-123F-4565-9164-39C4925E467B}") as string;
            if (!string.IsNullOrEmpty(val))
            {
                var p = Environment.ExpandEnvironmentVariables(val).TrimEnd('\\', '/');
                if (!string.IsNullOrEmpty(p)) return p;   // 盘暂时没挂也照样记住
            }
        }
        catch { /* 回落 */ }

        var home = Environment.GetEnvironmentVariable("USERPROFILE") ?? HomeDir;
        if (!string.IsNullOrEmpty(home)) return Path.Combine(home, "Downloads");
        return @"C:\Users\" + (Environment.GetEnvironmentVariable("USERNAME") ?? "user") + @"\Downloads";
    }

    public static string DefaultOutDir() => WindowsDownloadDir();

    /// <summary>
    /// 目录记忆规则：首次→下载文件夹；用户改过→一直沿用；
    /// 旧默认 Z:\太极营 且本机不存在→回落；自定目录盘没挂→仍记住，不偷改。
    /// </summary>
    public static string EffectiveOutDir(AppConfig cfg)
    {
        var d = cfg?.out_dir ?? "";
        if (string.IsNullOrWhiteSpace(d)) return DefaultOutDir();
        if (LegacyOutDirs.Contains(d) && !Directory.Exists(d)) return DefaultOutDir();
        return d;
    }

    public static string Serialize<T>(T value) => JsonSerializer.Serialize(value, JsonOpt);
    public static T Deserialize<T>(string text) => JsonSerializer.Deserialize<T>(text, JsonOpt);
}
