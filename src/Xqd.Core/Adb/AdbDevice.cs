using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using Xqd.Core;

namespace Xqd.Core.Adb;

/// <summary>
/// ADB 旧路径的设备驱动 —— 对照 xqd.py 全文 + xqd_app.py 的导航/课表部分。
///
/// 已验证事实（docs/01 一/二/四/五节）：
///  · ADB 可执行文件 D:\Program Files\Netease\MuMu\nx_main\adb.exe，设备 192.168.1.101:5555（桥接），
///    包名 com.qlchat.xingqudao，缓存 /sdcard/Android/data/.../PlayerCache/txcache。
///  · 启动 App 必须用 monkey（-c android.intent.category.LAUNCHER 1），MainActivity 不存在。
///  · WebView 滚动慢速约 1200ms（快速 fling 无效），先滚到顶部。
///  · 一次 uiautomator dump 就含整营全部课名；课名进列表页时已知，不是播放后反推。
///  · 播放器按一次 BACK 回列表且滚动位置保留。
///  · 所有子进程走 Xqd.Core.Proc（无窗 + 环境净化）；Windows 下 shell 路径用正斜杠。
/// </summary>
internal sealed class AdbDevice
{
    // ── 常量（与已验证事实一致，勿改） ──────────────────────────────
    private const string AdbExe = @"D:\Program Files\Netease\MuMu\nx_main\adb.exe";
    public const string Device = "192.168.1.101:5555";
    public const string Pkg = "com.qlchat.xingqudao";
    public const string Remote =
        "/sdcard/Android/data/com.qlchat.xingqudao/files/PlayerCache/txcache";

    private readonly string _uiDir;
    private readonly string _uiFile;

    // 业务 fileId 提取（清单正文）
    private static readonly Regex BizIdRe1 =
        new(@"/([0-9a-f]{8})(\d{10,})/", RegexOptions.Compiled);
    private static readonly Regex BizIdRe2 =
        new("\"fileId\"\\s*:\\s*\"?(\\d{15,25})", RegexOptions.Compiled);
    private static readonly Regex CourseFallbackRe =
        new(@"(tvName|course|Course)", RegexOptions.Compiled);
    private static readonly Regex UrlRe =
        new(@"https?://[^\s""']+", RegexOptions.Compiled);

    public AdbDevice()
    {
        _uiDir = Path.Combine(Config.ToolDir, "adb_cache");
        _uiFile = Path.Combine(_uiDir, "_ui.xml");   // 本地 Windows 路径（back-slash 由 OS 处理）
        try { Directory.CreateDirectory(_uiDir); } catch { /* ignore */ }
    }

    // ── 底层：所有子进程走 Proc（无窗 + 环境净化 + MSYS_NO_PATHCONV=1） ──

    /// <summary>
    /// 子进程环境：Proc.CleanEnv() 净化 QT_*/QML*/_PYI_*/_MEIPASS2（避免 MuMu Qt5 弹窗），
    /// 再补 MSYS_NO_PATHCONV=1（docs/01 一节：Windows 下 shell 路径用正斜杠）。
    /// </summary>
    private static Dictionary<string, string> ChildEnv()
    {
        var env = Proc.CleanEnv();
        env["MSYS_NO_PATHCONV"] = "1";
        return env;
    }

    /// <summary>等价 xqd.adb(*args)：构造 [adb, -s, DEVICE, ...args] 并交给 Proc.Run。</summary>
    private Proc.RunResult AdbT(int timeoutMs, params string[] args)
    {
        var list = new List<string> { "-s", Device };
        list.AddRange(args);
        return Proc.Run(AdbExe, list, timeoutMs, null, ChildEnv());
    }

    /// <summary>连接设备（桥接）。对应 xqd.connect。</summary>
    public void Connect()
    {
        AdbT(30000, "connect", Device);
        Thread.Sleep(1000);
    }

    /// <summary>
    /// uiautomator dump → 本地文本。对应 xqd.ui_dump。
    /// 远端路径用正斜杠；本地落盘后按 UTF-8（replace）读。
    /// </summary>
    public string UiDump()
    {
        string remote = "/sdcard/_xqd_ui_"
                        + (DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() % 100000000) + ".xml";
        AdbT(90000, "shell", "uiautomator dump " + remote);
        try { if (File.Exists(_uiFile)) File.Delete(_uiFile); } catch { /* ignore */ }
        AdbT(90000, "pull", remote, _uiFile);
        if (!File.Exists(_uiFile)) return "";
        try { return File.ReadAllText(_uiFile, Encoding.UTF8); } catch { return ""; }
    }

    public void Tap(int x, int y, double wait = 0.0)
    {
        AdbT(30000, "shell", "input tap " + x + " " + y);
        if (wait > 0) Thread.Sleep((int)(wait * 1000));
    }

    /// <summary>一次 BACK 回课程列表页，且滚动位置保留（docs/01 二节）。</summary>
    public void Back(double wait = 1.8)
    {
        AdbT(30000, "shell", "input keyevent KEYCODE_BACK");
        Thread.Sleep((int)(wait * 1000));
    }

    /// <summary>
    /// input swipe。ms=1200 为 WebView 慢速（快速 fling 无效）；
    /// 营列表（RecyclerView）用 ms=300。
    /// </summary>
    public void Swipe(int x1, int y1, int x2, int y2, int ms = 1200, double wait = 1.6)
    {
        AdbT(60000, "shell", $"input swipe {x1} {y1} {x2} {y2} {ms}");
        Thread.Sleep((int)(wait * 1000));
    }

    /// <summary>启动 App：monkey（MainActivity 不存在）。对应 xqd.launch_app。</summary>
    public void LaunchApp()
    {
        AdbT(60000, "shell",
            "monkey -p " + Pkg + " -c android.intent.category.LAUNCHER 1");
        Thread.Sleep(7000);
    }

    /// <summary>确保 App 在前台，返回当前 XML。对应 xqd.wake_app。</summary>
    public string WakeApp()
    {
        var xml = UiDump();
        var k = Ui.PageKind(xml);
        if (k == "empty" || k == "desktop" || k == "unknown")
        {
            LaunchApp();
            xml = UiDump();
        }
        return xml;
    }

    // ── 导航：学习页 / 筛选标签 / 大课程页 / 课程列表页 ─────────────

    /// <summary>进入「学习」大课程列表页。对应 xqd.open_learning。</summary>
    public string OpenLearning()
    {
        for (int i = 0; i < 10; i++)
        {
            var xml = UiDump();
            var k = Ui.PageKind(xml);
            if (k == "learn_list" || (k == "unknown" && Ui.LearnCards(xml).Count > 0))
                return xml;
            var tabs = Ui.FindNodes(xml, "学习").Where(n => n.Y > 1400).ToList();
            if (tabs.Count > 0) { Tap(tabs[0].Cx, tabs[0].Cy, 4); continue; }
            if (k == "empty" || k == "desktop") { LaunchApp(); Thread.Sleep(2000); continue; }
            Back(2.5);
        }
        return UiDump();
    }

    /// <summary>切到指定筛选标签，返回新 XML。对应 xqd._switch_tab。</summary>
    public string SwitchTab(string xml, string tab)
    {
        UiNode hit = null;
        foreach (var n in Ui.FindNodes(xml))
        {
            if (n.Text == tab && n.Id.EndsWith("/tv_title", StringComparison.Ordinal)
                && n.Y > 200 && n.Y < 400) { hit = n; break; }
        }
        if (hit == null) return xml;
        Tap(hit.Cx, hit.Cy, 4.5);
        return UiDump();
    }

    /// <summary>切到指定标签（xqd_app.select_tab）：先回学习页再点标签。</summary>
    public string SelectTab(string tab, int tries = 3)
    {
        for (int i = 0; i < tries; i++)
        {
            var xml = OpenLearning();
            if (string.IsNullOrEmpty(xml)) continue;
            UiNode hit = null;
            foreach (var n in Ui.FindNodes(xml))
            {
                if (n.Text == tab && n.Id.EndsWith("/tv_title", StringComparison.Ordinal)
                    && n.Y > 200 && n.Y < 400) { hit = n; break; }
            }
            if (hit == null) continue;
            Tap(hit.Cx, hit.Cy, 4.5);
            xml = UiDump();
            if (Ui.IsLearnTab(xml)) return xml;
        }
        return UiDump();
    }

    /// <summary>
    /// 列出某标签下的所有营（滚到底采集，去重保持顺序）。对应 xqd_app.list_camps。
    /// ★ 找营必须先把列表滚到底 —— 首屏只有 3~5 个营。
    /// </summary>
    public List<CampInfo> ListCamps(string tab, bool scroll = true)
    {
        var xml = SelectTab(tab);
        var seen = new List<CampInfo>();
        var seenNames = new HashSet<string>(StringComparer.Ordinal);
        void Merge(List<CampInfo> list)
        {
            foreach (var c in list)
                if (seenNames.Add(c.Name)) seen.Add(c);
        }

        Merge(Ui.ParseCamps(xml));
        if (scroll)
        {
            int stagnant = 0;
            for (int i = 0; i < 40; i++)
            {
                int before = seen.Count;
                Swipe(450, 1300, 450, 700, 300, 1.5);
                xml = UiDump();
                if (!Ui.IsLearnTab(xml)) break;
                Merge(Ui.ParseCamps(xml));
                if (xml.IndexOf("没有更多了", StringComparison.Ordinal) >= 0) break;
                if (seen.Count == before) { stagnant++; if (stagnant >= 3) break; }
                else stagnant = 0;
            }
        }
        return seen;
    }

    /// <summary>
    /// 在当前标签页列表里找营，返回 (x, y) 或 null。
    /// ★ 找营必须先把列表滚到底（首屏只有 3~5 个营）。对应 xqd._find_camp_in_list。
    /// </summary>
    public (int x, int y)? FindCampInList(string xml, string campName, int tries = 30)
    {
        foreach (var c in Ui.CampCards(xml))
            if (c.text.IndexOf(campName, StringComparison.Ordinal) >= 0) return (c.x, c.y);
        for (int i = 0; i < tries; i++)
        {
            if (xml.IndexOf("没有更多了", StringComparison.Ordinal) >= 0) break;
            Swipe(450, 1300, 450, 700, 300, 1.6);
            xml = UiDump();
            if (Ui.PageKind(xml) != "learn_list") break;
            foreach (var c in Ui.CampCards(xml))
                if (c.text.IndexOf(campName, StringComparison.Ordinal) >= 0) return (c.x, c.y);
        }
        return null;
    }

    /// <summary>
    /// 进入指定营的【大课程页】（含「课程」图标）。营可能只在某个筛选标签下，
    /// 故跨标签逐个找。对应 xqd.open_camp_card。
    /// </summary>
    public string OpenCampCard(string campName, string[] tabs = null)
    {
        tabs = tabs ?? Ui.LearnTabs;
        for (int attempt = 0; attempt < 2; attempt++)
        {
            var xml = OpenLearning();
            if (string.IsNullOrEmpty(xml)) continue;
            (int x, int y)? tgt = null;
            foreach (var tab in tabs)
            {
                xml = SwitchTab(xml, tab);
                if (Ui.PageKind(xml) != "learn_list")
                {
                    xml = OpenLearning();
                    if (string.IsNullOrEmpty(xml)) continue;
                }
                tgt = FindCampInList(xml, campName);
                if (tgt != null) break;
            }
            if (tgt == null)
            {
                for (int i = 0; i < 20; i++) Swipe(450, 700, 450, 1300, 300, 1.1); // 滚回顶部
                continue;
            }
            Tap(tgt.Value.x, tgt.Value.y - 30, 8);
            xml = UiDump();
            if (xml.IndexOf("tvName", StringComparison.Ordinal) >= 0) return xml;
            Back(3);
        }
        return "";
    }

    /// <summary>在大课程页点「课程」图标 → 完整课程列表页。对应 xqd.open_course_tab。</summary>
    public string OpenCourseTab()
    {
        for (int i = 0; i < 8; i++)
        {
            var xml = UiDump();
            var nodes = Ui.FindNodes(xml);
            UiNode hit = null;
            foreach (var n in nodes) { if (n.Text == "课程") { hit = n; break; } }

            if (hit != null)
            {
                Tap(hit.Cx, hit.Cy, 5);
                var x2 = UiDump();
                if (Ui.PageKind(x2) == "course_list") return x2;
                xml = x2;
                continue;
            }
            // 兜底：找 tvName / course 相关 id
            bool broke = false;
            foreach (var n in nodes)
            {
                if (!CourseFallbackRe.IsMatch(n.Id)) continue;
                Tap(n.Cx, n.Cy, 5);
                var x2 = UiDump();
                if (Ui.PageKind(x2) == "course_list") return x2;
                xml = x2;
                broke = true;
                break;
            }
            if (!broke) return "";           // 对应 Python for...else
            Swipe(450, 1300, 450, 800, 300, 2.5);
        }
        return "";
    }

    /// <summary>一步到位进入某营完整课程列表页。对应 xqd.open_course_list。</summary>
    public string OpenCourseList(string campName)
    {
        var xml = OpenCampCard(campName);
        if (string.IsNullOrEmpty(xml)) return "";
        return OpenCourseTab();
    }

    // ── 课表采集（WebView） ─────────────────────────────────────────

    /// <summary>慢速上滚到列表顶部（WebView 只认慢速拖动）。对应 xqd.scroll_top。</summary>
    public string ScrollTop(int times = 26)
    {
        for (int i = 0; i < times; i++) Swipe(450, 700, 450, 1250, 1200, 1.2);
        return UiDump();
    }

    /// <summary>慢速下滚一屏。对应 xqd.scroll_down。</summary>
    public void ScrollDown(double wait = 1.6) => Swipe(450, 1250, 450, 700, 1200, wait);

    /// <summary>
    /// 采集整个营的完整课表 [{title, when, index}]。对应 xqd.collect_catalog / xqd_app.camp_catalog。
    /// ★ 课名在「进入列表页时」就一次性读到（一次 dump 含整营全部课名），
    ///   不是播放后反推；滚动只是为把屏幕外卡片带进可点区域 / 兜底。
    /// </summary>
    public List<Card> CampCatalog(string campName)
    {
        var xml = OpenCourseList(campName);
        if (string.IsNullOrEmpty(xml)) return new List<Card>();
        int total = Ui.ListTotal(xml);
        xml = ScrollTop(28);

        var seen = new HashSet<string>(StringComparer.Ordinal);
        var order = new List<Card>();
        int stagnant = 0;
        for (int i = 0; i < 220; i++)
        {
            var cards = Ui.ListCards(xml);
            int added = 0;
            foreach (var c in cards)
            {
                if (c.Title.Length == 0) continue;
                var key = c.Title + "\u0001" + c.When;
                if (seen.Add(key))
                {
                    order.Add(new Card { Title = c.Title, When = c.When, Index = order.Count });
                    added++;
                }
            }
            if (total > 0 && order.Count >= total) break;
            if (added == 0) { stagnant++; if (stagnant >= 3) break; }
            else stagnant = 0;
            ScrollDown(1.6);
            xml = UiDump();
            if (Ui.PageKind(xml) != "course_list") break;
        }
        return order;
    }

    // ── 隐藏清单 / fileId（docs/01 五节） ──────────────────────────

    /// <summary>
    /// 远端隐藏清单 {文件名: (mtime串, size)}。
    /// Android `ls -la --full-time` 输出：
    ///   -rw-rw---- 1 u0_a52 ext_data_rw 1418 2026-11-07 02:16:06.770276400 +0800 .xxx.hls
    /// ★ 用 split() 逐字段读：parts[8]=文件名、parts[5]+parts[6]=mtime、parts[4]=大小；
    ///   不要用正则抠日期时间（反复出错）。对应 xqd.cache_state。
    /// </summary>
    public Dictionary<string, (string mtime, long size)> CacheState()
    {
        var r = AdbT(120000, "shell", "ls -la --full-time '" + Remote + "' 2>/dev/null");
        var st = new Dictionary<string, (string mtime, long size)>(StringComparer.Ordinal);
        foreach (var line in (r.Out ?? "").Replace("\r", "").Split('\n'))
        {
            var parts = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
            // 权限 链接数 属主 组 大小 日期 时间 时区 文件名
            if (parts.Length < 9 || !parts[0].StartsWith("-", StringComparison.Ordinal)) continue;
            long size = long.TryParse(parts[4], out var s) ? s : 0;
            st[parts[8]] = (parts[5] + " " + parts[6], size);
        }
        return st;
    }

    /// <summary>读隐藏清单正文。对应 xqd.read_manifest。</summary>
    public string ReadManifest(string fname) =>
        AdbT(60000, "shell", "cat '" + Remote + "/" + fname + "' 2>/dev/null").Out ?? "";

    /// <summary>从清单正文提取业务 fileId。对应 xqd.biz_ids。</summary>
    public List<string> BizIds(string text)
    {
        var ids = new List<string>();
        foreach (Match m in BizIdRe1.Matches(text ?? ""))
            if (!ids.Contains(m.Groups[2].Value)) ids.Add(m.Groups[2].Value);
        foreach (Match m in BizIdRe2.Matches(text ?? ""))
            if (!ids.Contains(m.Groups[1].Value)) ids.Add(m.Groups[1].Value);
        return ids;
    }

    /// <summary>清单正文里的第一个 http(s) URL（对应 xqd_app.URL_RE.search）。</summary>
    public string FirstUrl(string text)
    {
        var m = UrlRe.Match(text ?? "");
        return m.Success ? m.Value : "";
    }

    /// <summary>设备是否在线（CheckAuth 用，不启动模拟器、不读 Cookie）。</summary>
    public bool DeviceOnline()
    {
        Connect();
        var r = AdbT(30000, "shell", "echo xqd_ready");
        return r.Ok && (r.Out ?? "").IndexOf("xqd_ready", StringComparison.Ordinal) >= 0;
    }
}
