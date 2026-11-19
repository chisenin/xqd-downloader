using System;
using System.IO;
using System.Text;

namespace Xqd.Core;

/// <summary>
/// 凭据读取 —— 单一入口，代码里绝不硬编码 Cookie。
/// 优先级：XQD_COOKIE → QLD_COOKIE → %USERPROFILE%\.xqd_tool\cookie.txt。
/// </summary>
public static class Creds
{
    public static readonly string[] EnvKeys = { "XQD_COOKIE", "QLD_COOKIE" };

    public static string FromEnv()
    {
        foreach (var k in EnvKeys)
        {
            var v = (Environment.GetEnvironmentVariable(k) ?? "").Trim();
            if (!string.IsNullOrEmpty(v)) return v;
        }
        return "";
    }

    public static string FromFile()
    {
        try
        {
            if (!File.Exists(Config.CredFile)) return "";
            var raw = File.ReadAllText(Config.CredFile, Encoding.UTF8).Trim();
            if (string.IsNullOrEmpty(raw)) return "";
            var parts = new System.Collections.Generic.List<string>();
            foreach (var line in raw.Replace('\r', '\n').Split('\n'))
            {
                var s = line.Trim();
                if (s.Length > 0) parts.Add(s);
            }
            if (parts.Count > 1)
            {
                var allKv = true;
                foreach (var p in parts) if (!p.Contains('=')) { allKv = false; break; }
                if (allKv) return string.Join("; ", parts);
            }
            return raw;
        }
        catch (IOException) { return ""; }
    }

    public static string LoadCookie(bool required = false)
    {
        var cookie = FromEnv();
        if (string.IsNullOrEmpty(cookie)) cookie = FromFile();
        if (required && string.IsNullOrEmpty(cookie))
            throw new InvalidOperationException(
                "拿不到兴趣岛授权。请设置环境变量 XQD_COOKIE，或把 Cookie 写入 " + Config.CredFile);
        return cookie;
    }

    /// <summary>
    /// 落盘新授权供下次启动复用；XQD_TEST_HOME 下且未显式给 path 时拒绝写真实凭据。
    /// 用「临时文件 + 原子替换」，避免写一半留下截断凭据。
    /// </summary>
    public static bool SaveCookie(string cookie, string path = null)
    {
        cookie = (cookie ?? "").Trim();
        if (string.IsNullOrEmpty(cookie)) return false;
        if (path == null)
        {
            if (!string.IsNullOrEmpty(Config.TestHome)) return false;
            path = Config.CredFile;
        }
        var tmp = path + ".tmp";
        try
        {
            var folder = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(folder)) Directory.CreateDirectory(folder);
            File.WriteAllText(tmp, cookie + "\n", new UTF8Encoding(false));
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
            return true;
        }
        catch (IOException)
        {
            try { if (File.Exists(tmp)) File.Delete(tmp); } catch { /* ignore */ }
            return false;
        }
    }
}
