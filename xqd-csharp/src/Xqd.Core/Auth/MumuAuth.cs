using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
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
    // ★ v1.7.1：实例号不再写死 0 —— 多开时用户可能只开了实例 3，
    //   固定 -v 0 必然读不到 Cookie（换机器/换习惯就对不上）。
    //   _vmIndex 由 ChooseInstanceAsync 在流程开始时探出来（0~7 全探）。
    private const int MaxVmIndex = 8;          // 探 0..7
    private const string QianliaoPackage = "com.qlchat.xingqudao";
    private const string CookieDb =
        "/data/data/com.qlchat.xingqudao/app_webview/Default/Cookies";
    private const string MainProcess = "MuMuNxMain.exe";

    /// <summary>
    /// 记住用户手动选定的 MuMuManager.exe（换机器/换安装目录后由界面引导点选一次）。
    /// </summary>
    public static bool SetManagerPath(string path) => Setup.ToolLocator.RememberMumuManager(path);

    /// <summary>当前机器上定位到的 MuMuManager.exe（找不到抛 AuthException）。</summary>
    public static string FindMumu() => FindMumuManager();

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
    /// <summary>本次流程选中/探测到的 MuMu 实例号（-1 = 还没探）。</summary>
    private int _vmIndex = 0;
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

        // ★ v1.7.1：先探实例（0~7 全探），再决定对哪台操作 —— 绝不写死实例 0。
        _vmIndex = await ChooseInstanceAsync(manager, onStatus, ct).ConfigureAwait(false);

        // autoLaunch=false：设备没在跑就直接失败，绝不启动。
        if (!autoLaunch && !await IsRunningAsync(manager, _vmIndex, ct).ConfigureAwait(false))
            return Fail("MuMu / 安卓设备未运行。请先启动 MuMu 并在兴趣岛 App "
                        + "中登录，然后回到本工具点「重试」。");

        // ★ 直接确保设备：control launch 会连带拉起主程序（约 13 秒就绪）；
        //   绝不先 main launch —— 实测那样反而会卡住（docs/11 A）。
        if (!await EnsureDeviceAsync(manager, onStatus, ct).ConfigureAwait(false))
            return Fail($"安卓设备启动超时（240 秒，实例 {_vmIndex}）。");

        // ★ 换了台机器的常见剧本：MuMu 装了、实例也在跑，但这台实例里没装兴趣岛 App。
        //   不给出这一步，用户只会反复看到「App 未登录」，以为是登录问题。
        if (!await AppInstalledAsync(manager, ct).ConfigureAwait(false))
            return Fail("实例 " + _vmIndex + " 里没有「兴趣岛」App。"
                        + "\n\n请在 MuMu 的这个实例里安装并登录兴趣岛，然后回到本工具点「重试」。");

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
    //  边等边取（对应 hgvd 的 WaitForAuth / GUI WaitAuthWindow）
    // ════════════════════════════════════════════════════════════════

    /// <summary>等授权的结果。</summary>
    public sealed class WaitLoginResult
    {
        /// <summary>读到登录态的实例号；-1 = 没等到。</summary>
        public int Index = -1;
        public bool TimedOut;
        public string Message = "";
        public bool Ok => Index >= 0;
    }

    /// <summary>
    /// 每 2 秒扫一遍正在运行的实例，谁先出现「能拼出 userId + rsessionId」的登录态就返回谁。
    /// ★ 用户可能还没启动那台装了兴趣岛的安卓机、或 App 还没登录；
    ///   与其让用户对着「App 未登录」反复点重试，不如等他自己去操作。
    /// ★ 只负责「等到」，落盘仍由 EnsureAuthAsync 完成 —— 等待窗关掉后重跑一次授权即可。
    /// </summary>
    public static async Task<WaitLoginResult> WaitForLoginAsync(
        int timeoutSec, Action<string> onStatus, CancellationToken ct)
    {
        string manager = Setup.ToolLocator.FindMumuManager() ?? "";
        if (manager.Length == 0)
            return new WaitLoginResult
            {
                Message = "找不到 MuMuManager.exe，无法等待授权。"
                          + "请先在界面里点「指定 MuMuManager…」选一次。",
            };

        var probe = new MumuAuth();
        var deadline = DateTime.UtcNow.AddSeconds(Math.Max(5, timeoutSec));
        int lastRunning = -1;
        string lastError = "";

        while (DateTime.UtcNow < deadline)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                var insts = await probe.ListInstancesAsync(manager, ct).ConfigureAwait(false);
                var running = insts.Where(i => i.Started).OrderBy(i => i.Index).ToList();

                if (running.Count == 0)
                {
                    if (lastRunning != 0)
                    {
                        Say(onStatus, "还没有安卓实例在运行 —— 请打开 MuMu，"
                                      + "启动那台装了「兴趣岛」的安卓机。");
                        lastRunning = 0;
                    }
                }
                else
                {
                    foreach (var inst in running)
                    {
                        ct.ThrowIfCancellationRequested();
                        try
                        {
                            if (!await probe.AppInstalledOnAsync(manager, inst.Index, ct)
                                      .ConfigureAwait(false))
                                continue;
                            var header = await probe.ReadHeaderOnAsync(manager, inst.Index, ct)
                                                    .ConfigureAwait(false);
                            if (!string.IsNullOrEmpty(header))
                            {
                                Say(onStatus, $"✓ 实例 {inst.Index} 已登录，正在读取…");
                                return new WaitLoginResult
                                {
                                    Index = inst.Index,
                                    Message = $"实例 {inst.Index} 已登录",
                                };
                            }
                        }
                        catch (OperationCanceledException) { throw; }
                        catch { /* 这台读不到，下轮再看 */ }
                    }

                    if (lastRunning != running.Count)
                    {
                        Say(onStatus, $"检测到 {running.Count} 台实例在运行，"
                                      + "正在等「兴趣岛」登录态…（请在 App 里确认已登录）");
                        lastRunning = running.Count;
                    }
                }
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception e)
            {
                // 读失败不代表没登录，继续等；同一个错误只播报一次
                if (lastError != e.Message)
                {
                    Say(onStatus, "等待中：" + e.Message);
                    lastError = e.Message;
                }
            }

            await Task.Delay(2_000, ct).ConfigureAwait(false);
        }

        return new WaitLoginResult
        {
            TimedOut = true,
            Message = $"等待 {timeoutSec} 秒仍未读到登录态。"
                      + "请在 MuMu 里确认：安卓机已启动 → 兴趣岛 App 已安装 → 已登录。",
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
    private static string[] ManagerCmd(int index, string sub, params string[] extra)
    {
        var list = new List<string>
        {
            sub, "-v", index.ToString(CultureInfo.InvariantCulture)
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

    /// <summary>
    /// 定位 MuMuManager.exe：点选记录 → 环境变量 → 各盘常规安装位置（深搜限 2 层）→ PATH。
    /// ★ 具体探测规则集中在 Setup/ToolLocator，本文件不再持有任何盘符常量。
    /// </summary>
    private static string FindMumuManager()
    {
        string found = Setup.ToolLocator.FindMumuManager();
        if (!string.IsNullOrEmpty(found)) return found;

        throw new AuthException(
            "找不到 MuMuManager.exe。请确认已安装网易 MuMu 模拟器，"
            + "或在界面里点选一次 MuMu 安装目录 nx_main 下的 MuMuManager.exe。");
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

    /// <summary>一个 MuMu 安卓实例（多开时每台是独立安卓系统）。</summary>
    public sealed class MumuInstance
    {
        public int Index;
        public bool Started;
        public string Name = "";
        public override string ToString() =>
            $"实例 {Index}" + (Started ? "（运行中）" : "（未启动）");
    }

    /// <summary>
    /// 枚举 0~7 号实例（MuMuManager info -v i）。
    /// ★ 必须全探：用户可能只开了实例 2，不能「0/1 没启动就收工」。
    /// </summary>
    public async Task<List<MumuInstance>> ListInstancesAsync(string manager, CancellationToken ct)
    {
        var list = new List<MumuInstance>();
        for (int i = 0; i < MaxVmIndex; i++)
        {
            ct.ThrowIfCancellationRequested();
            JsonElement info;
            try
            {
                var r = await RunAsync(manager, ManagerCmd(i, "info"), InfoTimeoutMs, ct)
                              .ConfigureAwait(false);
                if (string.IsNullOrWhiteSpace(r.Out)) continue;
                info = J.Parse(r.Out);
            }
            catch (OperationCanceledException) { throw; }
            catch { continue; }        // 该实例不存在 / 输出不是 JSON

            var root = info;
            if (root.ValueKind == JsonValueKind.Array)
            {
                var arr = root.EnumerateArray().ToList();
                if (arr.Count == 0) continue;
                root = arr[0];
            }
            if (root.ValueKind != JsonValueKind.Object) continue;
            if (!root.TryGetProperty("index", out _) && !root.TryGetProperty("is_android_started", out _))
                continue;              // 不是正常 info 返回

            list.Add(new MumuInstance
            {
                Index = (int)J.Long(root, "index", i),
                Started = J.Bool(root, "is_android_started", false),
                Name = J.Str(root, "name", "实例 " + i),
            });
        }
        return list;
    }

    /// <summary>
    /// 选出本次要用的实例。
    /// ★ 多开时不能只按「最近修改时间」猜，也不能固定实例 0：
    ///   逐台试读 Cookie，取第一台真的有 userId + rsessionId 的；
    ///   多台都有登录态时再联网验证，取服务端认可的那台；
    ///   全都读不到就退回「第一台运行中的」，把 App 拉起来让用户登录。
    /// </summary>
    private async Task<int> ChooseInstanceAsync(string manager, Action<string> onStatus,
                                                CancellationToken ct)
    {
        var insts = await ListInstancesAsync(manager, ct).ConfigureAwait(false);
        var running = insts.Where(i => i.Started).OrderBy(i => i.Index).ToList();

        if (running.Count == 0)
        {
            int idx = insts.Count > 0 ? insts.OrderBy(i => i.Index).First().Index : 0;
            Say(onStatus, $"没有实例在运行，准备启动实例 {idx}…");
            return idx;
        }

        // 只有一台在跑：直接用它（最常见）
        if (running.Count == 1)
        {
            Say(onStatus, $"使用实例 {running[0].Index}（{running[0].Name}）");
            return running[0].Index;
        }

        // 多开：逐台试读
        var candidates = new List<(int Index, string Header)>();
        foreach (var inst in running)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                // 先看这台上有没有装兴趣岛 App —— 没装的读了也白读
                if (!await AppInstalledOnAsync(manager, inst.Index, ct).ConfigureAwait(false)) continue;
                var header = await ReadHeaderOnAsync(manager, inst.Index, ct).ConfigureAwait(false);
                if (!string.IsNullOrEmpty(header)) candidates.Add((inst.Index, header));
            }
            catch (OperationCanceledException) { throw; }
            catch { /* 这台读不到，跳过 */ }
        }

        if (candidates.Count == 0)
        {
            Say(onStatus, $"检测到 {running.Count} 台实例在运行，但都没读到登录态；"
                          + $"先用实例 {running[0].Index}");
            return running[0].Index;
        }
        if (candidates.Count == 1)
        {
            Say(onStatus, $"使用实例 {candidates[0].Index}（已读到登录态）");
            return candidates[0].Index;
        }

        // 多台都有 cookie：联网验证，取服务端认可的那台
        foreach (var c in candidates)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                var p = new Xqd.Core.Api.QianliaoPlatform(c.Header);
                var (ok, _) = await p.CheckAuthAsync(ct).ConfigureAwait(false);
                if (ok)
                {
                    Say(onStatus, $"使用实例 {c.Index}（授权在线验证有效）");
                    return c.Index;
                }
            }
            catch (OperationCanceledException) { throw; }
            catch { /* 网络不通就继续 */ }
        }

        // 全都验证不了（可能断网）：退第一台读得到的，并提示
        Say(onStatus, $"授权无法在线验证，先使用实例 {candidates[0].Index}");
        return candidates[0].Index;
    }

    /// <summary>在指定实例上读一次 Cookie 头（读不到返回空，不抛）。</summary>
    private async Task<string> ReadHeaderOnAsync(string manager, int index, CancellationToken ct)
    {
        var command = "sqlite3 '" + CookieDb + "' \"" + CookieQuery + "\"";
        var (outText, ok) = await ShellAsync(manager, index, command, ShellTimeoutMs, ct)
                                  .ConfigureAwait(false);
        if (VmNotRunning(outText)) return "";
        if (!ok && string.IsNullOrWhiteSpace(outText)) return "";

        var cookies = ParseCookies(outText, out var missing);
        return missing.Count == 0 ? BuildHeader(cookies) : "";
    }

    /// <summary>player_info：info -v N 的 JSON；失败返回 default(JsonElement)（等价 {}）。</summary>
    private async Task<JsonElement> PlayerInfoAsync(string manager, int index, CancellationToken ct)
    {
        try
        {
            var r = await RunAsync(manager, ManagerCmd(index, "info"), InfoTimeoutMs, ct)
                          .ConfigureAwait(false);
            return J.Parse(r.Out);
        }
        catch (Exception e) when (!(e is OperationCanceledException))
        {
            return default;   // 解析失败 / 进程异常 → 视作未启动
        }
    }

    /// <summary>is_running：info 的 is_android_started。</summary>
    private async Task<bool> IsRunningAsync(string manager, int index, CancellationToken ct)
    {
        var info = await PlayerInfoAsync(manager, index, ct).ConfigureAwait(false);
        if (info.ValueKind == JsonValueKind.Array)
        {
            var arr = info.EnumerateArray().ToList();
            info = arr.Count > 0 ? arr[0] : default;
        }
        return J.Bool(info, "is_android_started");
    }

    /// <summary>launch_player：control -v N launch。</summary>
    private async Task<bool> LaunchPlayerAsync(string manager, int index, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager, ManagerCmd(index, "control", "launch"), ControlTimeoutMs, ct)
                  .ConfigureAwait(false);
            return true;
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>shutdown_player：control -v N shutdown。</summary>
    private async Task<bool> ShutdownPlayerAsync(string manager, int index, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager, ManagerCmd(index, "control", "shutdown"), ControlTimeoutMs, ct)
                  .ConfigureAwait(false);
            return true;
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>wait_until_ready：轮询 info 直到 is_android_started=true。</summary>
    private async Task<bool> WaitUntilReadyAsync(string manager, int index,
                                                Action<string> onStatus,
                                                CancellationToken ct, int timeoutMs)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < timeoutMs)
        {
            ct.ThrowIfCancellationRequested();
            if (await IsRunningAsync(manager, index, ct).ConfigureAwait(false))
            {
                Say(onStatus, $"安卓设备已就绪（实例 {index}，{sw.Elapsed.TotalSeconds:0}s）");
                return true;
            }
            Say(onStatus, $"等待安卓设备启动… 实例 {index}，{sw.Elapsed.TotalSeconds:0}s");
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
        if (!force && await IsRunningAsync(manager, _vmIndex, ct).ConfigureAwait(false))
            return true;   // 已在跑（用户自己开的），不标记会话

        Say(onStatus, $"安卓设备未启动，正在启动实例 {_vmIndex}…");
        await LaunchPlayerAsync(manager, _vmIndex, ct).ConfigureAwait(false);
        if (!await WaitUntilReadyAsync(manager, _vmIndex, onStatus, ct, DeviceReadyTimeoutMs)
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
    private async Task<(string Out, bool Ok)> ShellAsync(string manager, int index, string command,
                                                         int timeoutMs, CancellationToken ct)
    {
        try
        {
            var r = await RunAsync(manager, ManagerCmd(index, "sh", "-c", command), timeoutMs, ct)
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

    /// <summary>launch_app：control -v N app launch --package &lt;pkg&gt;。</summary>
    private async Task<bool> LaunchAppAsync(string manager, CancellationToken ct)
    {
        try
        {
            await RunAsync(manager,
                          ManagerCmd(_vmIndex, "control", "app", "launch", "--package", QianliaoPackage),
                          ControlTimeoutMs, ct).ConfigureAwait(false);
            return true;
        }
        catch (Exception e) when (!(e is OperationCanceledException)) { return false; }
    }

    /// <summary>app_installed：pm list packages 是否含该包（指定实例）。</summary>
    private async Task<bool> AppInstalledOnAsync(string manager, int index, CancellationToken ct)
    {
        var (outText, _) = await ShellAsync(
            manager, index, "pm list packages " + QianliaoPackage, 30_000, ct)
            .ConfigureAwait(false);
        return outText.Contains("package:" + QianliaoPackage);
    }

    /// <summary>app_installed：当前实例。</summary>
    private Task<bool> AppInstalledAsync(string manager, CancellationToken ct) =>
        AppInstalledOnAsync(manager, _vmIndex, ct);

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
                           ManagerCmd(_vmIndex, "control", "app", "close", "--package", QianliaoPackage),
                           ControlTimeoutMs, ct).ConfigureAwait(false);
        }
        catch (Exception e) when (!(e is OperationCanceledException))
        { /* 失败仍继续 force-stop */ }
        await ShellAsync(manager, _vmIndex, "am force-stop " + QianliaoPackage, 30_000, ct)
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
                manager, _vmIndex, "pidof " + QianliaoPackage, 15_000, ct).ConfigureAwait(false);
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
        if (!await ShutdownPlayerAsync(manager, _vmIndex, ct).ConfigureAwait(false)) return false;
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < ShutdownWaitMs)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                if (!await IsRunningAsync(manager, _vmIndex, ct).ConfigureAwait(false)) break;
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
    /// sqlite3 输出 → {name: CookieVal}，并算出缺失的必需字段。
    /// ★ 顶层域（host 以 '.' 开头）优先：同名 cookie 取 .qianliao.net 那条。
    /// </summary>
    private static Dictionary<string, CookieVal> ParseCookies(string outText, out List<string> missing)
    {
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

            if (!cookies.TryGetValue(name, out var existing) || (domainPref && !existing.DomainPref))
                cookies[name] = new CookieVal { Value = value, DomainPref = domainPref };
        }

        missing = new List<string>();
        foreach (var name in RequiredCookies)
            if (!cookies.TryGetValue(name, out var required) || string.IsNullOrEmpty(required.Value))
                missing.Add(name);
        return cookies;
    }

    /// <summary>拼 Cookie 请求头（必需 + 有值才带的可选字段）。绝不输出任何值到日志。</summary>
    private static string BuildHeader(Dictionary<string, CookieVal> cookies)
    {
        var parts = new List<string>();
        foreach (var name in RequiredCookies)
            if (cookies.TryGetValue(name, out var required) && !string.IsNullOrEmpty(required.Value))
                parts.Add(name + "=" + required.Value);
        foreach (var name in OptionalCookies)
            if (cookies.TryGetValue(name, out var optional) && !string.IsNullOrEmpty(optional.Value))
                parts.Add(name + "=" + optional.Value);
        return string.Join("; ", parts);
    }

    /// <summary>
    /// read_app_cookies：sqlite3 读 App WebView Cookie 库（当前实例）。
    /// ★ 设备已停 → 抛 VmNotRunningException，由主流程触发 ensure_device 重启。
    /// </summary>
    private async Task<Dictionary<string, CookieVal>> ReadAppCookiesAsync(
        string manager, CancellationToken ct)
    {
        var command = "sqlite3 '" + CookieDb + "' \"" + CookieQuery + "\"";
        var (outText, ok) = await ShellAsync(manager, _vmIndex, command, ShellTimeoutMs, ct)
                                  .ConfigureAwait(false);

        if (VmNotRunning(outText)) throw new VmNotRunningException();
        if (!ok && string.IsNullOrWhiteSpace(outText))
            throw new AuthException("读取 Cookie 库失败（sqlite3 无输出）。");

        var cookies = ParseCookies(outText, out var _);
        return cookies;
    }

    /// <summary>
    /// get_cookie_header：拼出可直接用的 Cookie 请求头值。
    /// 必需 userId + rsessionId；可选 caller/platform/ver/deviceType/os。
    /// ★ 绝不硬编码 Cookie 值；缺必需项时异常只报**字段名**，不报任何值。
    /// </summary>
    private async Task<string> GetCookieHeaderAsync(string manager, CancellationToken ct)
    {
        var command = "sqlite3 '" + CookieDb + "' \"" + CookieQuery + "\"";
        var (outText, ok) = await ShellAsync(manager, _vmIndex, command, ShellTimeoutMs, ct)
                                  .ConfigureAwait(false);
        if (VmNotRunning(outText)) throw new VmNotRunningException();
        if (!ok && string.IsNullOrWhiteSpace(outText))
            throw new AuthException("读取 Cookie 库失败（sqlite3 无输出）。");

        var cookies = ParseCookies(outText, out var missing);
        if (missing.Count > 0)
            throw new AppNotLoginException(
                "App 未登录（缺少 " + string.Join("、", missing) + "）。");
        return BuildHeader(cookies);
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
    //  诊断（--authcheck）：给「换机器拿不到授权」一个自证入口
    // ════════════════════════════════════════════════════════════════

    /// <summary>
    /// 打印：MuMuManager 实际路径 + 0~7 各实例的启动/登录状态 + 最终会选哪台。
    /// ★ 只报「有没有登录态」，绝不输出任何 cookie 值。
    /// </summary>
    public static async Task<string> DiagnoseAsync(CancellationToken ct = default)
    {
        var sb = new System.Text.StringBuilder();
        string manager = Setup.ToolLocator.FindMumuManager() ?? "";
        sb.AppendLine("MuMuManager：" + (manager.Length > 0 ? manager : "（未找到）"));
        if (manager.Length == 0)
        {
            sb.AppendLine();
            sb.AppendLine("→ 请确认已安装 MuMu，或在界面里点「指定 MuMuManager…」选一次。");
            return sb.ToString();
        }

        var auth = new MumuAuth();
        var insts = await auth.ListInstancesAsync(manager, ct).ConfigureAwait(false);
        sb.AppendLine($"实例数：{insts.Count}");
        foreach (var inst in insts)
        {
            string login = "未登录";
            if (inst.Started)
            {
                try
                {
                    var header = await auth.ReadHeaderOnAsync(manager, inst.Index, ct).ConfigureAwait(false);
                    login = header.Length > 0 ? "✓ 有登录态" : "✗ 没有 userId/rsessionId";
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception e) { login = "读取失败：" + e.Message; }
            }
            sb.AppendLine($"  实例 {inst.Index}  {(inst.Started ? "运行中" : "未启动")}  {inst.Name}  {login}");
        }

        var chosen = await auth.ChooseInstanceAsync(manager, null, ct).ConfigureAwait(false);
        sb.AppendLine($"→ 会使用实例 {chosen}");
        return sb.ToString();
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
