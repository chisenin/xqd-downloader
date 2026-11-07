using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace Xqd.Core;

/// <summary>
/// 无控制台窗口 + Qt 环境净化的子进程封装。对应 Python 的 xqd_proc.py。
///
/// 两个已验证的根治点：
///  1) GUI 程序启动控制台子系统程序（MuMuManager / tasklist / ffmpeg）会弹黑框
///     → CreateNoWindow + Hidden。
///  2) PySide6(Qt6) 注入的 QT_PLUGIN_PATH 会被 MuMu 的 Qt5 程序继承，
///     弹「no Qt platform plugin」→ 每次创建子进程时净化 QT_*/QML*/_PYI_*，
///     并对 MuMuManager 显式指向其自带 Qt5 plugins 目录、剔除 _MEI*/PySide6 PATH。
///     ★ 净化必须在**子进程创建处**做（孙进程同样继承），不要改自己进程的环境。
/// </summary>
public static class Proc
{
    private static readonly Regex MeiDirRe =
        new(@"_MEI\d{3,}", RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly string[] QtPrefixes = { "QT_", "QML" };
    private static readonly string[] PyiPrefixes = { "_PYI_" };
    private static readonly string[] PyiKeys = { "_MEIPASS2" };

    public sealed class RunResult
    {
        public int Code { get; set; } = -1;
        public string Out { get; set; } = "";
        public string Err { get; set; } = "";
        public bool Ok => Code == 0;
    }

    private static Dictionary<string, string> CurrentEnv()
    {
        var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (DictionaryEntry e in Environment.GetEnvironmentVariables())
        {
            var k = e.Key?.ToString() ?? "";
            if (k.Length > 0) d[k] = e.Value?.ToString() ?? "";
        }
        return d;
    }

    public static Dictionary<string, string> CleanEnv(IDictionary<string, string> baseEnv = null)
    {
        var src = baseEnv != null
            ? new Dictionary<string, string>(baseEnv, StringComparer.OrdinalIgnoreCase)
            : CurrentEnv();
        var env = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var kv in src)
        {
            var up = kv.Key.ToUpperInvariant();
            if (QtPrefixes.Any(p => up.StartsWith(p, StringComparison.Ordinal))) continue;
            if (PyiPrefixes.Any(p => up.StartsWith(p, StringComparison.Ordinal))) continue;
            if (PyiKeys.Any(k => up == k)) continue;
            env[kv.Key] = kv.Value;
        }
        return env;
    }

    private static string MumuDir(string exe)
    {
        if (string.IsNullOrEmpty(exe)) return "";
        try
        {
            if (string.Equals(Path.GetFileName(exe), "MuMuManager.exe",
                              StringComparison.OrdinalIgnoreCase))
                return Path.GetDirectoryName(Path.GetFullPath(exe)) ?? "";
        }
        catch { /* ignore */ }
        return "";
    }

    private static string StripPyiPaths(string path)
    {
        var kept = new List<string>();
        foreach (var part in (path ?? "").Split(Path.PathSeparator))
        {
            if (string.IsNullOrEmpty(part)) continue;
            if (MeiDirRe.IsMatch(part)) continue;
            if (string.Equals(Path.GetFileName(part.TrimEnd('\\', '/')), "PySide6",
                              StringComparison.OrdinalIgnoreCase)) continue;
            kept.Add(part);
        }
        return string.Join(Path.PathSeparator.ToString(), kept);
    }

    public static ProcessStartInfo StartInfo(string exe, IEnumerable<string> args = null,
                                             string workDir = null,
                                             IDictionary<string, string> env = null,
                                             bool redirectInput = false)
    {
        var psi = new ProcessStartInfo
        {
            FileName = exe,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = redirectInput,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        if (args != null)
            foreach (var a in args) psi.ArgumentList.Add(a);

        var childEnv = env != null
            ? new Dictionary<string, string>(env, StringComparer.OrdinalIgnoreCase)
            : CleanEnv();
        if (env == null)
        {
            var md = MumuDir(exe);
            if (!string.IsNullOrEmpty(md))
            {
                var plugins = Path.Combine(md, "plugins");
                var platforms = Path.Combine(plugins, "platforms");
                if (Directory.Exists(platforms))
                {
                    childEnv["QT_PLUGIN_PATH"] = plugins;
                    childEnv["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms;
                }
                childEnv["PATH"] = StripPyiPaths(
                    childEnv.TryGetValue("PATH", out var p) ? p : "");
                if (string.IsNullOrEmpty(workDir)) workDir = md;
            }
        }
        psi.Environment.Clear();
        foreach (var kv in childEnv)
            if (!string.IsNullOrEmpty(kv.Key)) psi.Environment[kv.Key] = kv.Value;

        if (!string.IsNullOrEmpty(workDir)) psi.WorkingDirectory = workDir;
        return psi;
    }

    public static RunResult Run(string exe, IEnumerable<string> args = null,
                                int timeoutMs = 60000, string workDir = null,
                                IDictionary<string, string> env = null,
                                string stdin = null, Encoding inputEncoding = null)
    {
        var psi = StartInfo(exe, args, workDir, env, stdin != null);
        using var p = new Process { StartInfo = psi };
        try
        {
            if (!p.Start()) return new RunResult { Code = -1, Err = "进程启动失败" };
        }
        catch (Exception e) { return new RunResult { Code = -1, Err = e.Message }; }

        if (stdin != null)
        {
            try
            {
                var enc = inputEncoding ?? new UTF8Encoding(false);
                p.StandardInput.Write(stdin);
                p.StandardInput.Close();
            }
            catch { /* ignore */ }
        }

        var so = p.StandardOutput.ReadToEndAsync();
        var se = p.StandardError.ReadToEndAsync();
        bool exited;
        if (timeoutMs > 0) exited = p.WaitForExit(timeoutMs);
        else { p.WaitForExit(); exited = true; }
        if (!exited)
        {
            try { p.Kill(true); } catch { /* ignore */ }
            p.WaitForExit(5000);
            return new RunResult { Code = -9, Err = "超时" };
        }
        string outText = "", errText = "";
        try { outText = so.GetAwaiter().GetResult(); } catch { /* ignore */ }
        try { errText = se.GetAwaiter().GetResult(); } catch { /* ignore */ }
        return new RunResult { Code = p.ExitCode, Out = outText, Err = errText };
    }

    public static string CheckOutput(string exe, IEnumerable<string> args = null,
                                     int timeoutMs = 60000, string workDir = null,
                                     IDictionary<string, string> env = null)
    {
        var r = Run(exe, args, timeoutMs, workDir, env);
        if (!r.Ok) throw new InvalidOperationException(
            $"{Path.GetFileName(exe)} 返回 {r.Code}：{r.Err}");
        return r.Out;
    }

    public static Process Popen(string exe, IEnumerable<string> args = null,
                                string workDir = null, IDictionary<string, string> env = null)
    {
        var psi = StartInfo(exe, args, workDir, env);
        var p = new Process { StartInfo = psi };
        p.Start();
        return p;
    }

    /// <summary>读 PE 头 Subsystem：2=GUI，3=控制台（仅调试用）。</summary>
    public static bool IsConsoleApp(string path)
    {
        try
        {
            var head = new byte[1024];
            using (var f = File.OpenRead(path)) f.Read(head, 0, head.Length);
            if (head[0] != (byte)'M' || head[1] != (byte)'Z') return false;
            var pe = BitConverter.ToInt32(head, 0x3c);
            if (pe + 0x5e > head.Length) return false;
            if (head[pe] != (byte)'P' || head[pe + 1] != (byte)'E') return false;
            return BitConverter.ToUInt16(head, pe + 0x5c) == 3;
        }
        catch { return false; }
    }
}
