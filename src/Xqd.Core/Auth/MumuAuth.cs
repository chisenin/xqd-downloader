using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Xqd.Core.Auth;

/// <summary>
/// 兴趣岛授权获取（免 adbd 通道）—— 对应 Python 的 xqd_auth.py / xqd_creds.py。
///
/// 原理：兴趣岛 App 是 WebView 壳，登录态明文存在
///   /data/data/com.qlchat.xingqudao/app_webview/Default/Cookies
/// 的 value 列（encrypted_value 为空）。用 MuMu 自带 MuMuManager.exe 的 sh
/// 子命令走**模拟器内部 RPC**（不是 adbd、root 上下文）执行 sqlite3 读表。
///
/// ★ 平时启动绝不启动 MuMu：forceMumu=false 时优先 Creds.LoadCookie()，
///   拿到就直接 FromCache=true 返回；只有本机没有保存授权 / forceMumu=true
///   才走模拟器，成功后 Creds.SaveCookie() 落盘复用（docs/10 授权段、docs/11 M）。
/// ★ 全部子进程一律走 Xqd.Core.Proc（无窗 + Qt 环境净化 + MuMu Qt5 插件修正），
///   绝不自己 Process.Start；这里用 Task.Run 把阻塞的 Proc.Run 挪到线程池，
///   等待一律用 Task.Delay(ct)，保证 async 可取消、不阻塞调用方（GUI）线程。
/// ★ 凭据绝不硬编码；异常 / 状态播报绝不携带 Cookie 值。
/// </summary>
public sealed class MumuAuth : IAuthService
{
    // ── 已验证的常量（docs/01 〇之二、docs/11 A）─────────────────────
    private const int VmIndex = 0;
    private const string QianliaoPackage = "com.qlchat.xingqudao";
    private const string CookieDb =
        "/data/data/com.qlchat.xingqudao/app_webview/Default/Cookies";
    private const string MainProcess = "MuMuNxMain.exe";

    private static readonly string[] MumuRootCandidates =
    {
        @"D:\Program Files\Netease\MuMu",
        @"C:\Program Files\Netease\MuMu",
        @"D:\Program Files\Netease\MuMu Player",
        @"C:\Program Files\Netease\MuMu Player",
    };

    // 必需 userId + rsessionId；可选字段缺失不影响鉴权。
    private static readonly string[] RequiredCookies = { "userId", "rsessionId" };
    private static readonly string[] OptionalCookies =
        { "caller", "platform", "ver", "deviceType", "os" };

    /// <summary>
    /// ★ SQL 必须是单百分号 '%qianliao%'：写成 '%%qianliao%%' 是**字面匹配
    ///   两个百分号**，一条都匹配不到（旧 Python 实现的坑，docs/11 A4）。
    ///   域名覆盖 .qianliao.net / .xqdaolove.cn / .nicegoods.cn（后者实测也
    ///   会写 rsessionId）。sqlite3 输出用 | 分隔，避免值里的逗号破坏解析。
    /// </summary>
    private const string CookieQuery =
        "select host_key,name,value from cookies "
        + "where host_key like '%qianliao%' "
        + "   or host_key like '%xqdaolove%' "
        + "   or host_key like '%nicegoods%';";

    // 各类子进程 / 轮询超时（对齐 xqd_auth.py 的 timeout 数值，毫秒）。
    private const int InfoTimeoutMs = 30_000;
    private const int ControlTimeoutMs = 60_000;
    private const int ShellTimeoutMs = 60_000;
    private const int DeviceReadyTimeoutMs = 240_000;
    private const int ShutdownWaitMs = 90_000;
    private const int AppStoppedTimeoutMs = 20_000;
    private const int PollMs = 3_000;
    private const int MaxCookieAttempts = 3;

    // ── 会话状态（对应 xqd_auth._SESSION）───────────────────────────
    // Services.Auth 是进程内单例，故用实例字段即可跨多次 EnsureAuthAsync
    // 保留：只记录**本工具启动的** main/device，供 CloseAll 判定该关谁。
    // 这样「App 未登录 → 去登录 → 点重试」第二次跑时依然认得出是谁启动的。
    private bool _sessionMain;
    private bool _sessionDevice;
    /// <summary>最近一次定位到的 MuMuManager.exe，供无参 CloseAll() 收尾复用。</summary>
    private string _manager = "";

    // ── 内部异常（对应 AuthError / 流程分支）─────────────────────────
    private class AuthException : Exception
    {
        public AuthException(string message) : base(message) { }
    }

    private sealed class AppNotLoginException : AuthException
    {
        public AppNotLoginException(string message) : base(message) { }
    }

    /// <summary>设备已停：sh 返回 {"errcode":-201,"errmsg":"vm not running"}。</summary>
    private sealed class VmNotRunningException : AuthException
    {
        public VmNotRunningException() : base("安卓设备未运行，无法读取 Cookie 库。") { }
    }

    private sealed class CookieVal
    {
        public string Value = "";
        public bool DomainPref;   // host 以 '.' 开头 → 顶层域（优先）
    }

    // ════════════════════════════════════════════════════════════════
    //  IAuthService
    // ════════════════════════════════════════════════════════════════

    /// <summary>
    /// 平时直接用保存的授权（不启动 MuMu）；仅首次 / forceMumu=true 才走模拟器。
    /// 对应 xqd_gui.auto_check_auth(force_mumu) + AuthWorker.run() 的组合。
    /// </summary>
    public async Task<AuthResult> EnsureAuthAsync(bool forceMumu = false,
                                                  Action<string> onStatus = null,
                                                  bool autoLaunch = true,
                                                  bool autoClose = true,
                                                  CancellationToken ct = default)
    {
        // ★ 缓存优先分支必须放在**任何** MuMu 调用之前：forceMumu=false 且本机
        //   已有授权时，一个 MuMuManager 都不调（连 find 都不做）。
        if (!forceMumu)
        {
            string cached;
            try { cached = Creds.LoadCookie(); }
            catch { cached = ""; }
            if (!string.IsNullOrEmpty(cached))
                return new AuthResult
                {
                    Ok = true,
                    Cookie = cached,
                    FromCache = true,
                    Message = "已使用本机保存的授权，未启动 MuMu 模拟器。",
                };
        }

        try
        {
            return await EnsureViaMumuAsync(onStatus, autoLaunch, autoClose, ct)
                         .ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            return Fail("授权已取消。");
        }
        catch (Exception e)
        {
            // 我方异常消息一律不含凭据内容；这里只透出诊断文本。
            return Fail("授权失败：" + e.Message);
        }
    }

    /// <summary>「重新授权」：强制走模拟器刷新，忽略缓存（docs/11 M 第二层）。</summary>
    public Task<AuthResult> RefreshAsync(Action<string> onStatus = null,
                                         CancellationToken ct = default) =>
        EnsureAuthAsync(true, onStatus, true, true, ct);   // forceMumu / autoLaunch / autoClose

    /// <summary>
    /// 收尾：按 autoClose 语义（会话状态）停 App / 关设备 / 关主程序。
    /// 只关本工具自己启动的组件；会话为空（用户自己开的窗口）时不动。
    /// 对应 xqd_auth.close_all(manager)。同步 void 契约，内部同步等待完成
    /// （链上所有 await 均 ConfigureAwait(false)，不会在 UI 线程死锁）。
    /// </summary>
    public void CloseAll()
    {
        try { CloseAllCoreAsync(_manager, CancellationToken.None).GetAwaiter().GetResult(); }
        catch { /* 收尾失败不影响退出 */ }
    }

    private static AuthResult Fail(string message) =>
        new AuthResult { Ok = false, Message = message ?? "" };

    // ════════════════════════════════════════════════════════════════
    //  模拟器主流程（对应 xqd_auth.ensure_auth + GUI AuthWorker.run）
    // ════════════════════════════════════════════════════════════════

    private async Task<AuthResult> EnsureViaMumuAsync(Action<string> onStatus,
                                                     bool autoLaunch,
                                                     bool autoClose,
                                                     CancellationToken ct)
    {
        string manager;
        try { manager = FindMumuManager(); }
        catch (AuthException ex) { return Fail(ex.Message); }
        _manager = manager;
        Say(onStatus, "MuMu 管理器：" + manager);

        // autoLaunch=false：设备没在跑就直接失败，绝不启动。
        if (!autoLaunch && !await IsRunningAsync(manager, ct).ConfigureAwait(false))
            return Fail("MuMu / 安卓设备未运行。请先启动 MuMu 并在兴趣岛 App "
                        + "中登录，然后回到本工具点「重试」。");

        // ★ 直接确保设备：control launch 会连带拉起主程序（约 13 秒就绪）；
        //   绝不先 main launch —— 实测那样反而会卡住（docs/11 A）。
        if (!await EnsureDeviceAsync(manager, onStatus, ct).ConfigureAwait(false))
            return Fail("安卓设备启动超时（240 秒）。");

        Say(onStatus, "读取 App 授权…");

        // 设备可能被 MuMu 自己关掉：sh 返回 vm not running（不是空输出）→
        // 识别后重新 ensure_device 拉起，再重试读 Cookie，不误判成「未登录」。
        string header = null;
        AppNotLoginException notLogin = null;
        AuthException readError = null;
        for (int attempt = 0; attempt < MaxCookieAttempts; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                header = await GetCookieHeaderAsync(manager, ct).ConfigureAwait(false);
                notLogin = null;
                readError = null;
                break;
            }
            catch (VmNotRunningException)
            {
                Say(onStatus, "安卓设备已停止，正在重新拉起…");
                bool relaunched = await EnsureDeviceAsync(manager, onStatus, ct, force: true)
                                        .ConfigureAwait(false);
                if (!relaunched)
                {
                    readError = new AuthException("安卓设备重新启动失败。");
                    break;
                }
                if (attempt == MaxCookieAttempts - 1)
                {
                    readError = new AuthException("读取授权失败：安卓设备反复停止。");
                    break;
                }
                continue;
            }
            catch (AppNotLoginException ex) { notLogin = ex; break; }
            catch (AuthException ex) { readError = ex; break; }
        }

        if (notLogin != null)
        {
            // App 未登录：打开 App 让用户去登录。★ 此时绝不关闭设备（用户还要登录）。
            Say(onStatus, "未检测到登录态，正在打开兴趣岛 App…");
            await LaunchAppAsync(manager, ct).ConfigureAwait(false);
            return Fail(notLogin.Message
                + "\n\n已在模拟器中打开兴趣岛 App，请完成登录后回到本工具点「重试」。");
        }
        if (readError != null) return Fail(readError.Message);
        if (string.IsNullOrEmpty(header)) return Fail("读取 App 授权失败。");

        Say(onStatus, "授权获取成功");

        // 落盘供下次启动复用（SaveCookie 自带 XQD_TEST_HOME 隔离，读取不受影响）。
        bool saved;
        try { saved = Creds.SaveCookie(header); }
        catch { saved = false; }

        // 收尾：autoClose=true 且确实有本工具启动的组件时，按会话状态关掉。
        // 用户自己开的模拟器不自动关（docs/10「只关本工具自己启动的东西」）。
        if (autoClose && (_sessionMain || _sessionDevice))
        {
            Say(onStatus, "正在关闭模拟器…");
            try { await CloseAllCoreAsync(manager, ct).ConfigureAwait(false); }
            catch (Exception e) when (!(e is OperationCanceledException))
            { /* 关闭失败不影响授权结果 */ }
        }

        return new AuthResult
        {
            Ok = true,
            Cookie = header,
            FromCache = false,
            Message = "授权成功。"
                      + (saved ? "已保存到本机私有文件，下次启动无需模拟器。" : ""),
        };
    }

    // ════════════════════════════════════════════════════════════════
    //  子进程封装：所有外部程序一律走 Xqd.Core.Proc
    // ════════════════════════════════════════════════════════════════

    private static Task<Proc.RunResult> RunAsync(string exe, string[] args,
                                                int timeoutMs, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        return Task.Run(() => Proc.Run(exe, args, timeoutMs), ct);
    }

    /// <summary>
    /// 组装 MuMuManager 子命令参数（exe 由 Proc.Run 第一个参数单独传）。
    /// ★ 子命令在前、-v 在后：info -v 0 / sh -v 0 -c ... / control -v 0 launch。
    ///   写成 -v 0 info 会打印帮助并返回非 0（docs/01 〇之二）。
    /// ★ main 是全局子命令、不带 -v，另见 MainCmd。
    /// </summary>
    private static string[] ManagerCmd(string sub, params string[] extra)
    {
        var list = new List<string>
        {
            sub, "-v", VmIndex.ToString(CultureInfo.InvariantCulture)
        };
        if (extra != null && extra.Length > 0) list.AddRange(extra);
        return list.ToArray();
    }

    /// <summary>main 是全局子命令，不带 -v：main launch / main close。</summary>
    private static string[] MainCmd(string action) => new[] { "main", action };

    private static void Say(Action<string> onStatus, string msg)
    {
        if (onStatus == null) return;
        try { onStatus(msg); }
        catch { /* 前端回调异常不影响授权流程（对应 Python say 的 try/except） */ }
    }

    // ════════════════════════════════════════════════════════════════
    //  定位 / 模拟器状态（对应 find_mumu_manager / player_info / is_running …）
    // ════════════════════════════════════════════════════════════════

    /// <summary>环境变量 XQD_MUMU_MANAGER → 常见安装目录 → 递归兜底(限深 2) → PATH。</summary>
    private static string FindMumuManager()
    {
        var env = Environment.GetEnvironmentVariable("XQD_MUMU_MANAGER");
        if (!string.IsNullOrEmpty(env) && File.Exists(env)) return env;

        foreach (var root in MumuRootCandidates)
        {
            if (!Directory.Exists(root)) continue;
            foreach (var rel in new[]
                     {
                         @"nx_main\MuMuManager.exe", @"nx_main\MuMuManager.exe",
                         "MuMuManager.exe", @"nemu\MuMuManager.exe",
                     })
            {
                var p = Path.Combine(root, rel);
                if (File.Exists(p)) return p;
            }
            var found = SearchManager(root, 0);
            if (found != null) return found;
        }

        foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? "")
                 .Split(Path.PathSeparator))
        {
            if (string.IsNullOrWhiteSpace(dir)) continue;
            foreach (var name in new[] { "MuMuManager.exe", "MuMuManager" })
            {
                try
                {
                    var p = Path.Combine(dir.Trim().Trim('"'), name);
                    if (File.Exists(p)) return Path.GetFullPath(p);
                }
                catch { /* 跳过非法 PATH 项 */ }
            }
        }

        throw new AuthException(
            "找不到 MuMuManager.exe。请确认已安装网易 MuMu 模拟器，"
            + "或设置环境变量 XQD_MUMU_MANAGER 指向该文件。");
    }

    /// <summary>os.walk 的限深 2 兜底：depth 超过 2 的目录不再深入。</summary>
    private static string SearchManager(string dir, int depth)
    {
        if (depth > 2) return null;
        try
        {
            var direct = Path.Combine(dir, "MuMuManager.exe");
            if (File.Exists(direct)) return direct;
            foreach (var sub in Directory.EnumerateDirectories(dir))
            {
                var found = SearchManager(sub, depth + 1);
                if (found != null) return found;
            }
        }
        catch { /* 无权限目录跳过 */ }
        return null;
    }

    /// <summary>player_info：info -v 0 的 JSON；失败返回 default(JsonElement)（等价 {}）。</summary>
    private async Task<JsonElement> PlayerInfoAsync(string manager, CancellationToken ct)
    {
        try
        {
            var r = await RunAsync(manager, ManagerCmd("info"), InfoTimeoutMs, ct)
                          .ConfigureAwait(false);
            return J.Parse(r.Out);
        }
        catch (Exception e) when (!(e is OperationCanceledException))
        {
            return default;   // 解析失败 / 进程异常 → 视作未启动
        }
    }

    /// <summary>is_running：info 的 is_android_started。</summary>
    private async Task<bool> IsRunningAsync(string manager, CancellationToken ct)
    {
        var info = await PlayerInfoAsync(manager, ct).ConfigureAwait(false);
        return J.Bool(info, "is_android_started");
    }

    /// <summary>launch_player：control -v 0 launch。</summary>
    private async Task<bool> LaunchPlayerAsync(string manager, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager, ManagerCmd("control", "launch"), ControlTimeoutMs, ct)
                  .ConfigureAwait(false);
            return true;
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>shutdown_player：control -v 0 shutdown。</summary>
    private async Task<bool> ShutdownPlayerAsync(string manager, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager, ManagerCmd("control", "shutdown"), ControlTimeoutMs, ct)
                  .ConfigureAwait(false);
            return true;
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>wait_until_ready：轮询 info 直到 is_android_started=true。</summary>
    private async Task<bool> WaitUntilReadyAsync(string manager, Action<string> onStatus,
                                                CancellationToken ct, int timeoutMs)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < timeoutMs)
        {
            ct.ThrowIfCancellationRequested();
            if (await IsRunningAsync(manager, ct).ConfigureAwait(false))
            {
                Say(onStatus, $"安卓设备已就绪（{sw.Elapsed.TotalSeconds:0}s）");
                return true;
            }
            Say(onStatus, $"等待安卓设备启动… {sw.Elapsed.TotalSeconds:0}s");
            await Task.Delay(PollMs, ct).ConfigureAwait(false);
        }
        return false;
    }

    /// <summary>
    /// ensure_device：确保安卓设备在跑。
    /// ★ 绝不先 main launch（先 main launch 再 control launch 会卡住）；
    ///   control launch 会连带拉起主程序。设备起来后把连带的主程序也记进会话。
    /// force=true：跳过「已在运行」短路，强制重新 launch（读到 vm not running 后重启）。
    /// 返回是否就绪；本工具启动的组件记入 _sessionDevice / _sessionMain。
    /// </summary>
    private async Task<bool> EnsureDeviceAsync(string manager, Action<string> onStatus,
                                                CancellationToken ct, bool force = false)
    {
        if (!force && await IsRunningAsync(manager, ct).ConfigureAwait(false))
            return true;   // 已在跑（用户自己开的），不标记会话

        Say(onStatus, "安卓设备未启动，正在启动…");
        await LaunchPlayerAsync(manager, ct).ConfigureAwait(false);
        if (!await WaitUntilReadyAsync(manager, onStatus, ct, DeviceReadyTimeoutMs)
                  .ConfigureAwait(false))
            return false;

        _sessionDevice = true;
        _sessionMain = _sessionMain || await MainRunningAsync(ct).ConfigureAwait(false);
        return true;
    }

    /// <summary>
    /// ensure_main：单独确保主程序（多开器）在跑。
    /// ★ 这是对照 xqd_auth.ensure_main 保留的能力，**主授权流程不调用它** ——
    ///   实测先 main launch 反而会卡住，设备启动一律走 EnsureDeviceAsync 的
    ///   control launch 连带拉起（docs/11 A、docs/01 〇之二）。
    /// </summary>
    private async Task<bool> EnsureMainAsync(string manager, Action<string> onStatus,
                                             CancellationToken ct)
    {
        if (await MainRunningAsync(ct).ConfigureAwait(false)) return false;
        Say(onStatus, "正在启动 MuMu…");
        if (!await LaunchMainAsync(manager, ct).ConfigureAwait(false)) return false;
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < 30_000)
        {
            ct.ThrowIfCancellationRequested();
            if (await MainRunningAsync(ct).ConfigureAwait(false))
            {
                Say(onStatus, "MuMu 已启动");
                _sessionMain = true;
                return true;
            }
            await Task.Delay(1_000, ct).ConfigureAwait(false);
        }
        Say(onStatus, "MuMu 启动超时，继续尝试拉起安卓设备…");
        return false;
    }

    // ════════════════════════════════════════════════════════════════
    //  内部 RPC shell / App 控制（shell / launch_app / stop_app …）
    // ════════════════════════════════════════════════════════════════

    /// <summary>
    /// shell：sh -v 0 -c "command"（内部 RPC，非 adbd）。返回 (输出, 是否成功)。
    /// MuMuManager 的 sh 会把错误 JSON 混进 stdout；超时（Proc 返回 Code=-9）
    /// 不当作输出，避免把「超时」二字误当成 Cookie 行。
    /// </summary>
    private async Task<(string Out, bool Ok)> ShellAsync(string manager, string command,
                                                         int timeoutMs, CancellationToken ct)
    {
        try
        {
            var r = await RunAsync(manager, ManagerCmd("sh", "-c", command), timeoutMs, ct)
                          .ConfigureAwait(false);
            var text = r.Out;
            if (string.IsNullOrWhiteSpace(text) && r.Code != -9 &&
                !string.IsNullOrEmpty(r.Err))
                text = r.Err;
            return (text ?? "", r.Ok);
        }
        catch (Exception e) when (!(e is OperationCanceledException))
        {
            return ("", false);
        }
    }

    /// <summary>launch_app：control -v 0 app launch --package &lt;pkg&gt;。</summary>
    private async Task<bool> LaunchAppAsync(string manager, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager,
                          ManagerCmd("control", "app", "launch", "--package", QianliaoPackage),
                          ControlTimeoutMs, ct).ConfigureAwait(false);
            return true;
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>app_installed：pm list packages 是否含该包。</summary>
    private async Task<bool> AppInstalledAsync(string manager, CancellationToken ct)
    {
        var (outText, _) = await ShellAsync(
            manager, "pm list packages " + QianliaoPackage, 30_000, ct)
            .ConfigureAwait(false);
        return outText.Contains("package:" + QianliaoPackage);
    }

    /// <summary>
    /// vm_not_running：设备已停时 sh 返回
    /// {"errcode":-201,"errmsg":"vm not running, can not connect NemuShell !!"}，
    /// **不是空输出**；不识别会误判成「App 还活着 / 读到 Cookie」。
    /// </summary>
    private static bool VmNotRunning(string output)
    {
        if (string.IsNullOrEmpty(output)) return false;
        var low = output.ToLowerInvariant();
        return low.Contains("vm not running") || low.Contains("nemoshell")
               || low.Contains("\"errcode\"");
    }

    /// <summary>stop_app：control app close（官方通道）+ am force-stop 兜底。</summary>
    private async Task<bool> StopAppAsync(string manager, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager,
                           ManagerCmd("control", "app", "close", "--package", QianliaoPackage),
                           ControlTimeoutMs, ct).ConfigureAwait(false);
        }
        catch (Exception e) when (!(e is OperationCanceledException))
        { /* 失败仍继续 force-stop */ }
        await ShellAsync(manager, "am force-stop " + QianliaoPackage, 30_000, ct)
              .ConfigureAwait(false);
        return true;
    }

    /// <summary>wait_app_stopped：轮询 pidof；设备已停也算「已停止」。</summary>
    private async Task<bool> WaitAppStoppedAsync(string manager, CancellationToken ct)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < AppStoppedTimeoutMs)
        {
            ct.ThrowIfCancellationRequested();
            var (outText, _) = await ShellAsync(
                manager, "pidof " + QianliaoPackage, 15_000, ct).ConfigureAwait(false);
            if (VmNotRunning(outText)) return true;
            if (string.IsNullOrWhiteSpace(outText)) return true;
            await Task.Delay(1_000, ct).ConfigureAwait(false);
        }
        return false;
    }

    /// <summary>main_running：tasklist 查 MuMuNxMain.exe。</summary>
    private async Task<bool> MainRunningAsync(CancellationToken ct)
    {
        try
        {
            var r = await RunAsync("tasklist",
                                  new[] { "/FI", "IMAGENAME eq " + MainProcess },
                                  20_000, ct).ConfigureAwait(false);
            return (r.Out ?? "").ToLowerInvariant()
                   .Contains(MainProcess.ToLowerInvariant());
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>launch_main：main launch（全局子命令，不带 -v）。</summary>
    private async Task<bool> LaunchMainAsync(string manager, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager, MainCmd("launch"), 90_000, ct).ConfigureAwait(false);
            return true;
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>close_main：main close（全局子命令，不带 -v）。</summary>
    private async Task<bool> CloseMainAsync(string manager, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager, MainCmd("close"), ControlTimeoutMs, ct)
                  .ConfigureAwait(false);
            return true;
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>
    /// close_player：control shutdown 是**异步**的 → 轮询 info 直到
    /// is_android_started 变 False（约 28 秒），再多等 3 秒让磁盘落盘。
    /// </summary>
    private async Task<bool> ClosePlayerAsync(string manager, CancellationToken ct)
    {
        if (!await ShutdownPlayerAsync(manager, ct).ConfigureAwait(false)) return false;
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < ShutdownWaitMs)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                if (!await IsRunningAsync(manager, ct).ConfigureAwait(false)) break;
            }
            catch (Exception e) when (!(e is OperationCanceledException)) { break; }
            await Task.Delay(2_000, ct).ConfigureAwait(false);
        }
        await Task.Delay(3_000, ct).ConfigureAwait(false);
        return true;
    }

    /// <summary>
    /// close_all：停 App + 按会话状态关设备 / 主程序，最后清空会话。
    /// ★ 只关本工具自己启动的：会话为空时不碰用户自己开的窗口（含其 App）。
    /// </summary>
    private async Task CloseAllCoreAsync(string manager, CancellationToken ct)
    {
        var st = SessionState();
        if (!st.Main && !st.Device) return;   // 没有工具启动的组件，不收尾
        if (string.IsNullOrEmpty(manager)) return;

        try
        {
            await StopAppAsync(manager, ct).ConfigureAwait(false);
            await WaitAppStoppedAsync(manager, ct).ConfigureAwait(false);
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { /* 忽略 */ }

        if (st.Device) await ClosePlayerAsync(manager, ct).ConfigureAwait(false);
        if (st.Main) await CloseMainAsync(manager, ct).ConfigureAwait(false);

        ResetSession();
    }

    // ════════════════════════════════════════════════════════════════
    //  读 Cookie（read_app_cookies / get_cookie_header / check_auth）
    // ════════════════════════════════════════════════════════════════

    /// <summary>
    /// read_app_cookies：sqlite3 读 App WebView Cookie 库，返回 {name: value}。
    /// ★ 顶层域（host 以 '.' 开头）优先：同名 cookie 取 .qianliao.net 那条，
    ///   它对所有子域生效（docs/01 〇之二、docs/11 A5）。
    /// ★ 设备已停 → 抛 VmNotRunningException，由主流程触发 ensure_device 重启。
    /// </summary>
    private async Task<Dictionary<string, CookieVal>> ReadAppCookiesAsync(
        string manager, CancellationToken ct)
    {
        var command = "sqlite3 '" + CookieDb + "' \"" + CookieQuery + "\"";
        var (outText, ok) = await ShellAsync(manager, command, ShellTimeoutMs, ct)
                                  .ConfigureAwait(false);

        if (VmNotRunning(outText)) throw new VmNotRunningException();
        if (!ok && string.IsNullOrWhiteSpace(outText))
            throw new AuthException("读取 Cookie 库失败（sqlite3 无输出）。");

        var cookies = new Dictionary<string, CookieVal>(StringComparer.Ordinal);
        foreach (var raw in (outText ?? "").Split('\n'))
        {
            var line = raw.Trim();   // Trim 同时去掉行尾 \r（等价 splitlines）
            if (line.Length == 0 || !line.Contains("|")) continue;
            var parts = line.Split('|');
            if (parts.Length < 3) continue;
            var host = parts[0];
            var name = parts[1];
            var value = parts[2];
            bool domainPref = host.StartsWith(".", StringComparison.Ordinal);

            // 顶层域优先：仅当「还没有」或「已有非顶层域、当前是顶层域」时覆盖。
            if (!cookies.TryGetValue(name, out var existing)
                || (domainPref && !existing.DomainPref))
                cookies[name] = new CookieVal { Value = value, DomainPref = domainPref };
        }
        return cookies;
    }

    /// <summary>
    /// get_cookie_header：拼出可直接用的 Cookie 请求头值。
    /// 必需 userId + rsessionId；可选 caller/platform/ver/deviceType/os。
    /// ★ 绝不硬编码 Cookie 值；缺必需项时异常只报**字段名**，不报任何值。
    /// </summary>
    private async Task<string> GetCookieHeaderAsync(string manager, CancellationToken ct)
    {
        var cookies = await ReadAppCookiesAsync(manager, ct).ConfigureAwait(false);

        var missing = new List<string>();
        foreach (var name in RequiredCookies)
        {
            if (!cookies.TryGetValue(name, out var required)
                || string.IsNullOrEmpty(required.Value))
                missing.Add(name);
        }
        if (missing.Count > 0)
            throw new AppNotLoginException(
                "App 未登录（缺少 " + string.Join("、", missing) + "）。");

        var parts = new List<string>();
        foreach (var name in RequiredCookies)
            parts.Add(name + "=" + cookies[name].Value);
        foreach (var name in OptionalCookies)
        {
            if (cookies.TryGetValue(name, out var optional)
                && !string.IsNullOrEmpty(optional.Value))
                parts.Add(name + "=" + optional.Value);
        }
        return string.Join("; ", parts);
    }

    /// <summary>check_auth：只检查本地是否有可用授权（不联网）。对应 xqd_auth.check_auth。</summary>
    private async Task<(bool Ok, string Info)> CheckAuthAsync(string manager,
                                                             CancellationToken ct)
    {
        try
        {
            var header = await GetCookieHeaderAsync(manager, ct).ConfigureAwait(false);
            return (true, header);
        }
        catch (AuthException e) { return (false, e.Message); }
        catch (Exception e) when (!(e is OperationCanceledException))
        { return (false, "检查授权时出错：" + e.Message); }
    }

    // ════════════════════════════════════════════════════════════════
    //  会话状态（对应 session_state / reset_session）
    // ════════════════════════════════════════════════════════════════

    private (bool Main, bool Device) SessionState() => (_sessionMain, _sessionDevice);

    private void ResetSession()
    {
        _sessionMain = false;
        _sessionDevice = false;
    }
}
