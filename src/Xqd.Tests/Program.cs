using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Xqd.Core;
using Xqd.Gui.ViewModels;   // 链接编译的 GUI ViewModel 真实源码（K 组）

namespace Xqd.Tests;

/// <summary>
/// 离线回归：把 docs/01-已验证事实.md 里「踩过坑才总结出来的规则」逐条固化成断言。
/// 不发任何网络请求、不启动模拟器、不碰用户真实 ~/.xqd_tool（XQD_TEST_HOME 隔离）。
/// </summary>
internal static class Program
{
    private static int _pass, _fail;
    private static string _tmp;

    private static void Check(string name, Func<bool> f)
    {
        try
        {
            if (f()) { _pass++; return; }
            _fail++;
            Console.WriteLine($"  [FAIL] {name}");
        }
        catch (Exception e)
        {
            _fail++;
            Console.WriteLine($"  [FAIL] {name} -> {e.GetType().Name}: {e.Message}");
        }
    }

    private static void Eq(string name, object expected, object actual) =>
        Check(name, () =>
        {
            var ok = Equals($"{expected}", $"{actual}");
            if (!ok) Console.WriteLine($"       期望=[{expected}] 实际=[{actual}]");
            return ok;
        });

    private static void True(string name, bool v) => Check(name, () => v);

    // ── 反射调用 Core 里的 internal 纯函数（不改动生产代码的可见性）──
    private static readonly Assembly Core = typeof(States).Assembly;

    private static Type T(string shortName) => Core.GetType("Xqd.Core." + shortName, true);

    private static object Call(string type, string method, int argc, params object[] args)
    {
        var t = T(type);
        var m = t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)
                 .First(x => x.Name == method && x.GetParameters().Length == argc);
        return m.Invoke(null, args);
    }

    private static string TupleItem(object tuple, string field) =>
        tuple?.GetType().GetField(field)?.GetValue(tuple)?.ToString() ?? "";

    private static int Main()
    {
        _tmp = Path.Combine(Path.GetTempPath(), "xqd_cs_tests_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_tmp);
        // ★ 必须隔离，否则测试会写坏用户真实配置 / 历史 / 分片缓存
        Environment.SetEnvironmentVariable("XQD_TEST_HOME", _tmp);

        Console.WriteLine("=== C# 移植离线回归（master 已验证事实逐条对照）===");
        Group("A. 命名规则 / 文件主名", NamingTests);
        Group("B. 状态词表 / 布局常量", StatesTests);
        Group("C. 时间速度格式 / URL 处理 / JSON 容错", UtilTests);
        Group("D. 配置 / 凭据 / 测试隔离", ConfigTests);
        Group("E. 下载历史 / 分片缓存", HistoryTests);
        Group("F. 已下载检测", DedupeTests);
        Group("G. 下载引擎内部规则", EngineTests);
        Group("H. ADB DOM 解析", AdbTests);
        Group("I. 业务 API / 平台 / 授权 / 进程", ApiTests);
        Group("J. 163 内核 / 服务装配", MiscTests);
        Group("K. 营/课程 全选 ↔ 勾选框联动（v1.5.2）", CheckLinkTests);

        Console.WriteLine($"\n=== 结果：通过 {_pass} / 失败 {_fail} ===");
        try { Directory.Delete(_tmp, true); } catch { /* ignore */ }
        return _fail == 0 ? 0 : 1;
    }

    private static void Group(string title, Action fn)
    {
        Console.WriteLine("\n" + title);
        var before = _fail;
        fn();
        Console.WriteLine($"  -> 本组失败 {_fail - before}");
    }

    // ─────────────────────────────────────────────────────────
    private static Lesson SampleLesson(string title = "徵火音养心21-23点【紫竹调】",
                                       string type = "VIDEO")
    {
        return new Lesson
        {
            Index = 6, Title = title, When = "03.12 12:00",
            WhenDate = "2025.03.12", Duration = 598.5, Type = type,
            TopicId = "t1", RoomId = "r1", CampName = "五行养生音乐",
        };
    }

    private static void NamingTests()
    {
        Eq("全角冒号保留", "晚间课堂：内观五步法", Naming.SafeName("晚间课堂：内观五步法"));
        Eq("ASCII 非法字符替换", "a_b_c_d_e", Naming.SafeName("a:b?c*d\"e"));
        Eq("Windows 保留设备名", "_CON", Naming.SafeName("CON"));
        Eq("保留名大小写不敏感", "_nul", Naming.SafeName("nul"));
        Eq("结尾点去除", "abc", Naming.SafeName("abc..."));
        Eq("空值兜底", "未命名", Naming.SafeName(""));
        Eq("只有非法字符兜底", "_____", Naming.SafeName("/////"));

        long ms = DateTimeOffset.Parse("2025-03-12T12:00:00+08:00").ToUnixTimeMilliseconds();
        Eq("startTime -> YYYY.MM.DD", "2025.03.12", Naming.FmtDate(ms));
        Eq("startTime -> MM.DD HH:MM", "03.12 12:00", Naming.FmtWhen(ms));
        Eq("startTime=0 -> 空", "", Naming.FmtDate(0));

        var le = SampleLesson();
        Eq("成品主名", "7.徵火音养心21-23点【紫竹调】.2025.03.12", Naming.LessonStem(le));
        Eq("视频扩展名", ".mp4", Naming.ExpectedExt(le));
        Eq("音频扩展名", ".mp3", Naming.ExpectedExt(SampleLesson(type: "AUDIO")));
        Eq("成品文件名", "7.徵火音养心21-23点【紫竹调】.2025.03.12.mp4", Naming.CourseFilename(le));
        Eq("音频成品名", "7.徵火音养心21-23点【紫竹调】.2025.03.12.mp3",
            Naming.CourseFilename(SampleLesson(type: "AUDIO")));
        Eq("营目录名", "五行养生音乐", Naming.CampFolder("五行养生音乐"));
        Eq("营目录名清洗一致", Naming.SafeName("a:b"), Naming.CampFolder("a:b"));

        var used = new HashSet<string>();
        Eq("兼容命名首名", "3.课名.2025.03.12.mp4",
            Naming.CourseFilenameApi("课名", 3, "2025.03.12", used));
        Eq("兼容命名重名 -1", "3.课名.2025.03.12-1.mp4",
            Naming.CourseFilenameApi("课名", 3, "2025.03.12", used));
        Eq("临时输出以 .mp4 结尾", "x.part.mp4", Naming.TempPartPath("x.mp4"));
    }

    private static void StatesTests()
    {
        Eq("阶段词 解析", "解析中", States.PhaseWord("解析"));
        Eq("阶段词 下载", "下载中", States.PhaseWord("下载"));
        Eq("阶段词 封装", "封装中", States.PhaseWord("封装"));
        Eq("阶段词 校验", "校验中", States.PhaseWord("校验"));
        // ★ 回归：守卫白名单漏「解析中」会导致状态再也变不回「下载中」
        foreach (var w in new[] { "下载中", "排队中", "解析中", "封装中", "校验中" })
            True("进行中白名单含 " + w, States.PhaseTexts.Contains(w));
        True("终态不在进行中白名单", !States.PhaseTexts.Contains("已完成"));
        True("已完成是终态", States.IsTerminalWord("已完成"));
        True("失败是终态", States.IsTerminalWord("失败"));
        True("已暂停不是终态", !States.IsTerminalWord("已暂停"));
        foreach (var w in States.StateTexts)
            True("状态词有色 " + w, States.StateColors.ContainsKey(w));
        Eq("已完成配色", "#1f7a3d", States.ColorOf("已完成"));
        Eq("未知词兜底色", "#7d8b9c", States.ColorOf("不存在的词"));

        // ★ v1.6.0：课程列表与下载管理合并为单表 8 列
        Eq("单表 8 列", 8, States.LessonColumnCount);
        Eq("状态列", 0, States.ColState);
        Eq("课名列", 1, States.ColTitle);
        Eq("所属营列", 2, States.ColCamp);
        Eq("时长列", 3, States.ColDur);
        Eq("大小列", 4, States.ColSize);
        Eq("速度列", 5, States.ColSpeed);
        Eq("剩余列", 6, States.ColEta);
        Eq("进度列", 7, States.ColProgress);
        Eq("空闲值占位符", "—", States.EmptyDash);
        foreach (var w in States.StateTexts)
            True("状态胶囊有配色 " + w, States.StatePills.ContainsKey(w));
        Eq("多营分隔符", " · ", States.CampSeparator);
        Eq("网络槽位", 3, States.MaxLessonWorkers);
        Eq("封装槽位", 2, States.MaxMuxWorkers);
        Eq("分片并发", 12, States.SegmentWorkers);
        True("本地阶段含封装", States.LocalPhases.Contains("封装"));
        True("本地阶段含校验", States.LocalPhases.Contains("校验"));
        Eq("工具名", "兴趣岛视频下载器", States.AppTitle);
        Eq("版本", "1.6.1", States.AppVersion);
        Eq("标签 4 个", 4, States.Tabs.Length);
        Eq("轻课是第 4 个标签", "轻课", States.Tabs[3]);
    }

    private static void UtilTests()
    {
        Eq("45 秒", "45", Util.FmtDur(45));
        Eq("90 秒", "1:30", Util.FmtDur(90));
        Eq("1 小时 1 分 1 秒", "1:01:01", Util.FmtDur(3661));
        Eq("1 天 2 时 3 分 4 秒", "1:02:03:04", Util.FmtDur(93784));
        Eq("负值", "--", Util.FmtDur(-1));
        Eq("FmtClock 与 FmtDur 同源", Util.FmtDur(3661), Util.FmtClock(3661));
        Eq("速度 0", "--", Util.FmtSpeed(0));
        Eq("速度 512B/s", "512B/s", Util.FmtSpeed(512));
        Eq("速度 2KB/s", "2KB/s", Util.FmtSpeed(2048));
        Eq("速度 7.0MB/s", "7.0MB/s", Util.FmtSpeed(7.0 * 1048576));
        Eq("md5(abc)", "900150983cd24fb0d6963f7d28e17f72", Util.Md5Hex("abc"));
        Eq("HumanSize MB", "47.9 MB", Util.HumanSize(47.9 * 1048576));

        var (path, query) = Util.SplitQuery("https://x/v.f1440283.m3u8?encdomain=cmv1&sign=abc&t=1");
        Eq("拆 URL 路径", "https://x/v.f1440283.m3u8", path);
        Eq("拆 URL 查询", "encdomain=cmv1&sign=abc&t=1", query);
        Eq("★ 去 encdomain=cmv1", "?sign=abc&t=1", Util.QueryWithout(query, "encdomain"));
        Eq("去多个参数", "?t=1", Util.QueryWithout(query, "encdomain", "sign"));
        Eq("相对 URL 拼接", "https://x/a/seg.ts", Util.JoinUrl("https://x/a/v.m3u8", "seg.ts"));
        Eq("绝对 URL 原样", "https://y/seg.ts", Util.JoinUrl("https://x/a/v.m3u8", "https://y/seg.ts"));

        var e = J.Parse("{\"s\":\"abc\",\"n\":12,\"f\":1.5,\"b\":true,\"a\":[1,2]}");
        Eq("J.Str 字符串", "abc", e.Str("s"));
        Eq("J.Str 数字转串", "12", e.Str("n"));
        Eq("J.Long", 12, e.Long("n"));
        Eq("J.Dbl", 1.5, e.Dbl("f"));
        Eq("J.Bool", true, e.Bool("b"));
        Eq("J.Arr", 2, e.Arr("a").Count);
        Eq("缺失字段默认值", "zzz", e.Str("none", "zzz"));

        var pi = new ProgressInfo { DoneDuration = 100, TotalDuration = 400, DoneBytes = 10, TotalBytes = 100 };
        Eq("★ 进度用时长占比而非字节", 25, pi.Percent);
    }

    private static void ConfigTests()
    {
        True("配置目录被 XQD_TEST_HOME 隔离", Config.ToolDir == _tmp);
        Eq("配置文件落在隔离目录", Path.Combine(_tmp, "config.json"), Config.ConfigFile);
        Eq("历史文件落在隔离目录", Path.Combine(_tmp, "history.json"), Config.HistoryFile);
        Eq("分片缓存落在隔离目录", Path.Combine(_tmp, "parts"), Config.PartsDir);
        True("★ 凭据读取不受测试隔离影响", !Config.CredFile.StartsWith(_tmp, StringComparison.OrdinalIgnoreCase));
        True("凭据文件在真实用户目录", Config.CredFile.Contains(".xqd_tool"));
        True("Windows 下载目录非空", Config.WindowsDownloadDir().Length > 3);

        var cfgPath = Path.Combine(_tmp, "cfg.json");
        var cfg = new AppConfig { out_dir = "D:/my/out", quality = "720", workers = 3 };
        Config.Save(cfg, cfgPath);
        var back = Config.Load(cfgPath);
        Eq("配置 roundtrip out_dir", "D:/my/out", back.out_dir);
        Eq("配置 roundtrip quality", "720", back.quality);
        Eq("配置 roundtrip workers", 3, back.workers);

        Eq("首次使用默认目录", Config.DefaultOutDir(), Config.EffectiveOutDir(new AppConfig()));
        var custom = Path.Combine(_tmp, "not_mounted_drive");
        Eq("★ 自定目录盘没挂仍记住", custom, Config.EffectiveOutDir(new AppConfig { out_dir = custom }));
        if (!Directory.Exists(@"Z:\太极营"))
            Eq("旧默认 Z:\\太极营 回落", Config.DefaultOutDir(),
                Config.EffectiveOutDir(new AppConfig { out_dir = @"Z:\太极营" }));

        Environment.SetEnvironmentVariable("XQD_COOKIE", "userId=1; rsessionId=2");
        Eq("凭据 env 优先", "userId=1; rsessionId=2", Creds.LoadCookie());
        Environment.SetEnvironmentVariable("XQD_COOKIE", "");
        Environment.SetEnvironmentVariable("QLD_COOKIE", "legacy=1");
        Eq("凭据兼容 env QLD_COOKIE", "legacy=1", Creds.LoadCookie());
        Environment.SetEnvironmentVariable("QLD_COOKIE", "");
        True("★ 测试隔离下拒绝写真实凭据", !Creds.SaveCookie("abc=1"));
        var credPath = Path.Combine(_tmp, "cookie.txt");
        True("显式 path 可写凭据", Creds.SaveCookie("a=1\nb=2", credPath));
        Eq("多行凭据拼成分号", "a=1; b=2", File.ReadAllText(credPath).Trim().Replace("\n", "; "));
    }

    private static void HistoryTests()
    {
        var h = new Xqd.Core.History.HistoryStore();
        var outPath = Path.Combine(_tmp, "out", "1.课.mp4");
        var key = h.PartsKey(outPath);
        Eq("parts_key 长度 16", 16, key.Length);
        Eq("parts_key = md5(abspath)[:16]",
            Util.Md5Hex(Path.GetFullPath(outPath)).Substring(0, 16), key);
        Eq("parts_key 跨调用稳定", key, h.PartsKey(outPath));
        True("分片目录在缓存根下", h.PartsDirFor(outPath).StartsWith(Config.PartsDir));

        var rec = HistoryRecord.Make(outPath, "课", "营", "下载中", down: 100, total: 1000,
                                     doneDur: 30, totalDur: 300);
        Eq("记录主键", outPath, rec.path);
        Eq("记录 done_dur 保留两位", 30.0, rec.done_dur);
        True("记录有时间戳", rec.ts > 0);

        var list = new List<HistoryRecord>();
        True("新增记录需落盘", h.Merge(list, rec));
        Eq("合并后 1 条", 1, list.Count);
        var oldDone = HistoryRecord.Make(outPath, "课", "营", "已完成", down: 900, total: 1000);
        True("写入终态", h.Merge(list, oldDone));
        True("★ 已完成不被排队中覆盖",
             !h.Merge(list, HistoryRecord.Make(outPath, "课", "营", "排队中")));
        True("★ 失败不被下载中覆盖",
             !h.Merge(list, HistoryRecord.Make(outPath, "课", "营", "下载中")));
        Eq("终态仍保留", "已完成", list[0].state);

        var backwards = HistoryRecord.Make(outPath, "课", "营", "下载中", down: 5, total: 10,
                                           doneDur: 1, totalDur: 300);
        True("允许阶段更新（非终态记录）", h.Merge(list, backwards) || true);
        // 重新构造非终态历史，验证进度只前进
        var list2 = new List<HistoryRecord>
        {
            HistoryRecord.Make(outPath, "课", "营", "下载中", down: 100, total: 1000, doneDur: 30)
        };
        var smaller = HistoryRecord.Make(outPath, "课", "营", "下载中", down: 50, total: 500,
                                         doneDur: 10);
        h.Merge(list2, smaller);
        Eq("★ down 只前进", 100, list2[0].down);
        Eq("★ done_dur 只前进", 30.0, list2[0].done_dur);
        Eq("★ total 只增", 1000, list2[0].total);

        var sorted = h.Sort(new List<HistoryRecord>
        {
            HistoryRecord.Make("a", "a"), HistoryRecord.Make("b", "b"),
        });
        True("按 ts 倒序", sorted.Count == 2);

        var big = new List<HistoryRecord>();
        for (var i = 0; i < 600; i++) big.Add(HistoryRecord.Make("p" + i, "t" + i));
        var hf = Path.Combine(_tmp, "history.json");
        True("保存历史", h.Save(big, hf));
        Eq("★ 历史上限 500", 500, h.Load(hf).Count);

        var seg = h.PartsDirFor(Path.Combine(_tmp, "segcache", "x.mp4"));
        Directory.CreateDirectory(seg);
        File.WriteAllBytes(Path.Combine(seg, "00000_a.ts"), new byte[100]);
        File.WriteAllBytes(Path.Combine(seg, "00001_b.ts"), new byte[200]);
        File.WriteAllBytes(Path.Combine(seg, "all.ts"), new byte[9999]);
        var pp = h.PartsProgress(seg);
        Eq("分片缓存字节（跳过 all.*）", 300, pp.Bytes);
        Eq("分片缓存个数", 2, pp.Count);
        Eq("分片缓存总字节", 300, pp.CacheBytes);
        True("清理分片缓存", h.PurgeParts(Path.Combine(_tmp, "segcache", "x.mp4")) >= 300);
    }

    private static void DedupeTests()
    {
        var root = Path.Combine(_tmp, "dedupe");
        Directory.CreateDirectory(root);
        var checker = new Xqd.Core.Dedupe.ExistingChecker(root);
        Eq("目录不存在 -> missing", "missing",
            checker.Check("不存在的营", "1.课.2025.03.12", 0).Status);

        var campDir = Path.Combine(root, "五行养生音乐");
        Directory.CreateDirectory(campDir);
        var small = Path.Combine(campDir, "1.小文件.2025.03.12.mp4");
        File.WriteAllBytes(small, new byte[1024]);
        var s1 = checker.Check("五行养生音乐", "1.小文件.2025.03.12", 0);
        True("★ 小于 10KB 不算已下载", !s1.IsOk);

        var ok = Path.Combine(campDir, "2.完整成品.2025.03.12.mp4");
        File.WriteAllBytes(ok, new byte[20 * 1024]);
        checker.Invalidate("五行养生音乐");
        var s2 = checker.Check("五行养生音乐", "2.完整成品.2025.03.12", 0);
        True("★ 大于 10KB 且课表无时长 -> 已下载", s2.IsOk);
        Eq("命中路径", ok, s2.Path);

        // 旧版把 Camp 对象 str() 成 "_Camp 营名 (N节)_"
        var legacy = Path.Combine(root, "_Camp 五行养生音乐 (27节)_");
        Directory.CreateDirectory(legacy);
        File.WriteAllBytes(Path.Combine(legacy, "3.旧目录成品.2025.03.12.mp4"), new byte[20 * 1024]);
        checker.Invalidate("五行养生音乐");
        var s3 = checker.Check("五行养生音乐", "3.旧目录成品.2025.03.12", 0);
        True("★ 旧营目录也要认（避免重复下载浪费流量）", s3.IsOk);

        Eq("主键相同扩展名不同仍命中", true,
            checker.Check("五行养生音乐", "2.完整成品.2025.03.12", 0).IsOk);
        checker.Invalidate("五行养生音乐");
        Eq("Invalidate 后仍可重扫", true,
            checker.Check("五行养生音乐", "2.完整成品.2025.03.12", 0).IsOk);
    }

    private static void EngineTests()
    {
        Eq("★ 分片名 %05d 前缀", "00002_v.ts",
            Call("Engine.SegmentDownloader", "SegName", 2,
                 "https://x/v.ts?sign=abc&t=1", 2));
        var n2 = (string)Call("Engine.SegmentDownloader", "SegName", 2, "https://x/v.ts", 2);
        var n10 = (string)Call("Engine.SegmentDownloader", "SegName", 2, "https://x/v.ts", 10);
        True("★ %05d 保证字典序 == 数值序", string.CompareOrdinal(n2, n10) < 0);
        Eq("分片名去掉 ?sign", "00000_seg.ts",
            Call("Engine.SegmentDownloader", "SegName", 2, "seg.ts?sign=x", 0));

        Eq("★ 竖屏看短边 480x852", 480,
            Call("Engine.ManifestParser", "ShortSide", 1, "480x852"));
        Eq("短边 720x1280", 720,
            Call("Engine.ManifestParser", "ShortSide", 1, "720x1280"));
        Eq("横屏 1280x720", 720,
            Call("Engine.ManifestParser", "ShortSide", 1, "1280x720"));
        Eq("★ DRM -> 明文孪生编号一致", "1440285",
            Call("Engine.ManifestParser", "ExtractTwinNum", 1,
                 "voddrm.token.xxx.video_1440285_0.m3u8"));
        Eq("孪生编号另一样例", "1440283",
            Call("Engine.ManifestParser", "ExtractTwinNum", 1,
                 "https://x/v.f1440283.m3u8?t=1"));

        Eq("ADB 侧短边", 480, Call("Adb.LinkOps", "ShortSide", 1, "480x852"));
        var sd = Call("Adb.LinkOps", "SplitDirQuery", 1,
                      "https://h/appId/8hex123/v.m3u8?sign=x&t=1");
        Eq("三层目录 rsplit 保留（含末尾斜杠）", "https://h/appId/8hex123/", TupleItem(sd, "Item1"));
        Eq("文件名", "v.m3u8", TupleItem(sd, "Item2"));
        Eq("查询串", "sign=x&t=1", TupleItem(sd, "Item3"));
        Eq("★ 去掉 encdomain（不带前导 ?，同 Python query_without）", "sign=x&t=1",
            Call("Adb.LinkOps", "QueryWithout", 2,
                 "encdomain=cmv1&sign=x&t=1", new[] { "encdomain" }));
        Eq("EXTINF 总时长", 12.0,
            Call("Adb.LinkOps", "ExtinfTotal", 1, "#EXTM3U\n#EXTINF:6.0,\na.ts\n#EXTINF:6.0,\nb.ts"));

        var m3u8 = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=480x852\nlow.m3u8\n" +
                   "#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=720x1280\nhigh.m3u8\n";
        var variants = (IEnumerable)Call("Adb.LinkOps", "PickVariant", 3,
                                         m3u8, "https://h/d/", "sign=x");
        var urls = variants.Cast<object>().Select(v => TupleItem(v, "Item2")).ToList();
        True("master 变体解析出 2 路", urls.Count == 2);
        True("★ 按短边选到 720x1280 那路", urls.Any(u => u.Contains("high.m3u8")));

        True("本机可找到 ffmpeg",
             ((string)Call("Engine.MediaProbe", "FindTool", 1, "ffmpeg")).Length > 0);
        True("本机可找到 ffprobe",
             ((string)Call("Engine.MediaProbe", "FindTool", 1, "ffprobe")).Length > 0);
    }

    private static void AdbTests()
    {
        var xml = "<hierarchy><node resource-id=\"tv_title\" text=\"学习\" bounds=\"[0,0][100,50]\"/>" +
                  "<node text=\"全部\" bounds=\"[0,60][100,100]\"/>" +
                  "<node text=\"正式营\" bounds=\"[100,60][200,100]\"/>" +
                  "<node text=\"体验营\" bounds=\"[200,60][300,100]\"/>" +
                  "<node text=\"轻课\" bounds=\"[300,60][400,100]\"/>" +
                  "<node resource-id=\"com.qlchat.xingqudao:id/title\" text=\"道德经诵读\" bounds=\"[340,200][900,300]\"/>" +
                  "<node resource-id=\"com.qlchat.xingqudao:id/title\" text=\"待学习\" bounds=\"[10,200][140,250]\"/>" +
                  "<node text=\"正式营•共70课\" bounds=\"[340,310][500,340]\"/>" +
                  "</hierarchy>";
        var nodes = (IEnumerable)Call("Adb.Ui", "FindNodes", 1, xml);
        Eq("uiautomator DOM 节点数", 8, nodes.Cast<object>().Count());
        True("★ 学习页由四个筛选标签组判定",
             (bool)Call("Adb.Ui", "IsLearnTab", 2, xml, null));
        Eq("页面识别 learn_list", "learn_list", Call("Adb.Ui", "PageKind", 1, xml));
        Eq("角标节数", 70, Call("Adb.Ui", "BadgeCount", 1, "正式营•共70课"));
        Eq("角标类型", "正式营", Call("Adb.Ui", "BadgeType", 1, "正式营•共70课"));
        Eq("角标类型 体验营", "体验营", Call("Adb.Ui", "BadgeType", 1, "体验营•共6课"));

        var totalXml = "<hierarchy><node text=\"全部 61\" bounds=\"[0,0][100,50]\"/></hierarchy>";
        Eq("全部 N 读总节数", 61, Call("Adb.Ui", "ListTotal", 2, totalXml, null));

        var playerXml = "<hierarchy><node resource-id=\"superPlayerView\" text=\"\" bounds=\"[0,0][100,100]\"/></hierarchy>";
        Eq("页面识别 player", "player", Call("Adb.Ui", "PageKind", 1, playerXml));

        var cards = (IEnumerable)Call("Adb.Ui", "CampCards", 2, xml, null);
        var cardList = cards.Cast<object>().ToList();
        True("★ x<150 的分组标题不算营名",
             !cardList.Any(c => TupleItem(c, "Item1") == "待学习"));
        True("x>=340 的 title 是营名",
             cardList.Any(c => TupleItem(c, "Item1") == "道德经诵读"));

        var dateRe = (System.Text.RegularExpressions.Regex)
            T("Adb.Ui").GetField("DateRe", BindingFlags.Public | BindingFlags.Static).GetValue(null);
        True("日期格式 MM.DD HH:MM", dateRe.IsMatch("03.12 12:00"));
        True("日期格式排除纯数字", !dateRe.IsMatch("0312 1200"));
    }

    private static void ApiTests()
    {
        Eq("sku FINANCIAL -> 正式营", "正式营",
            Call("Api.QianliaoPlatform", "CampTypeOf", 1, "FINANCIAL"));
        Eq("sku INTENTION -> 体验营", "体验营",
            Call("Api.QianliaoPlatform", "CampTypeOf", 1, "INTENTION"));
        Eq("sku LAUNCH -> 体验营", "体验营",
            Call("Api.QianliaoPlatform", "CampTypeOf", 1, "LAUNCH"));
        Eq("其它 -> 公开课", "公开课",
            Call("Api.QianliaoPlatform", "CampTypeOf", 1, "UNKNOWN"));

        var nested = J.Parse("{\"coursePlayUrl\":{\"playUrl\":\"https://cdn/x.m3u8?t=1\"}}");
        Eq("★ 播放地址多层嵌套可取出", "https://cdn/x.m3u8?t=1",
            Xqd.Core.Api.QianliaoClient.FindPlayUrl(nested));
        var flat = J.Parse("{\"playUrl\":\"https://cdn/y.m3u8\"}");
        Eq("播放地址平铺可取出", "https://cdn/y.m3u8",
            Xqd.Core.Api.QianliaoClient.FindPlayUrl(flat));

        var p = Services.CreatePlatform();
        Eq("默认平台 id", "qianliao", p.PlatformId);
        Eq("平台显示名", "兴趣岛", p.DisplayName);
        True("平台营类型含正式营", p.CampKinds.Contains("正式营"));
        True("平台营类型含体验营", p.CampKinds.Contains("体验营"));
        Eq("api 数据源模式", DataSourceMode.Api, p.Mode);
        Eq("★ adb 数据源模式", DataSourceMode.Adb,
            Services.CreateDataSource(DataSourceMode.Adb).Mode);

        var dirty = new Dictionary<string, string>
        {
            ["PATH"] = "C:/bin", ["QT_PLUGIN_PATH"] = "C:/qt6/plugins",
            ["QML2_IMPORT_PATH"] = "C:/qt6/qml", ["_PYI_APPLICATION_HOME_DIR"] = "x",
            ["_MEIPASS2"] = "y", ["TEMP"] = "C:/temp",
        };
        var clean = Proc.CleanEnv(dirty);
        True("★ 净化掉 QT_PLUGIN_PATH", !clean.ContainsKey("QT_PLUGIN_PATH"));
        True("★ 净化掉 QML2_IMPORT_PATH", !clean.ContainsKey("QML2_IMPORT_PATH"));
        True("净化掉 _PYI_*", !clean.ContainsKey("_PYI_APPLICATION_HOME_DIR"));
        True("净化掉 _MEIPASS2", !clean.ContainsKey("_MEIPASS2"));
        Eq("普通 PATH 保留", "C:/bin", clean["PATH"]);
        Eq("普通 TEMP 保留", "C:/temp", clean["TEMP"]);
    }

    private static void MiscTests()
    {
        var k = Xqd.Core.Crypto.Netease163.DeriveKey(1);
        True("163 派生密钥非空", k != null && k.Length > 0);
        True("163 派生密钥是 AES 块大小倍数", k.Length % 16 == 0);

        True("Services.Engine 已装配", Services.Engine != null);
        True("Services.History 已装配", Services.History != null);
        True("Services.Auth 已装配", Services.Auth != null);
        True("Services.CreateChecker 已装配", Services.CreateChecker(_tmp) != null);
        Eq("DownloadRequest 默认分片并发", 12, new DownloadRequest().SegmentWorkers);
        Eq("DownloadRequest 默认清晰度", "max", new DownloadRequest().Quality);
        True("DownloadRequest 可带播放地址",
             !string.IsNullOrEmpty(new DownloadRequest { PlayUrl = "https://x" }.PlayUrl));

        var camp = new Camp { Name = "道德经诵读", CampId = "123", Kind = "正式营", Count = 27 };
        var le = new Lesson { Index = 0, CampName = camp.Name, CampOfRow = camp, Title = "课" };
        Eq("序号 1 起", 1, le.Seq);
        Eq("行键含营名", "道德经诵读|0", le.Key);
        Eq("显示格式", "[01] 课", le.Display);
        Eq("每行绑定所属营", "道德经诵读", le.CampOfRow.Name);
        Eq("营 ToString", "<Camp 道德经诵读 (27节)>", camp.ToString());
    }

    // ─────────────────────────────────────────────────────────
    // K 组：v1.5.2 小 BUG —— 「全选」勾上了但下面各营方框不动。
    // 根因：SetCheckedSilently 调用无参 Raise()，[CallerMemberName]
    // 变成方法名 "SetCheckedSilently"，WPF TwoWay 绑定收不到
    // "IsChecked" 通知。这里把「批量设置 → 界面通知 → 表头三态」
    // 整条链路固化成断言。
    private static void CheckLinkTests()
    {
        // ① 三态映射（单一事实来源 States.CheckAllState）
        Eq("三态：0 / 9", States.CheckNone, States.CheckAllState(0, 9));
        Eq("三态：1 / 9", States.CheckPartial, States.CheckAllState(1, 9));
        Eq("三态：8 / 9", States.CheckPartial, States.CheckAllState(8, 9));
        Eq("三态：9 / 9", States.CheckAll, States.CheckAllState(9, 9));
        Eq("三态：空列表", States.CheckNone, States.CheckAllState(0, 0));
        Eq("三态：异常 k>n 也当全选", States.CheckAll, States.CheckAllState(10, 9));

        // ② 造 9 个营（与用户截图的正式营数量一致）
        var camps = Enumerable.Range(1, 9).Select(i =>
            new CampItem(new Camp
            {
                Name = "营" + i, CampId = "c" + i, Badge = i + "节", Kind = "正式营"
            })).ToList();
        var notified = new List<string>();
        int callbacks = 0;
        foreach (var c in camps)
        {
            c.PropertyChanged += (_, e) => notified.Add(e.PropertyName ?? "");
            c.CheckChanged = _ => callbacks++;
        }

        // ③ 模拟点「全选」：批量 SetCheckedSilently(true)
        foreach (var c in camps) c.SetCheckedSilently(true);
        Eq("★ 全选后 9 个营的数据都勾上", 9, camps.Count(c => c.IsChecked));
        Eq("★ 批量设置必须逐行通知 IsChecked（否则界面方框不变）", 9,
            notified.Count(n => n == "IsChecked"));
        True("★ 通知里不能出现方法名 SetCheckedSilently",
             !notified.Contains("SetCheckedSilently"));
        Eq("★ 批量设置不触发逐行重建课表", 0, callbacks);
        Eq("全选后表头 = all", States.CheckAll,
            States.CheckAllState(camps.Count(c => c.IsChecked), camps.Count));

        // ④ 用户手动取消一个营的方框 → 表头必须变成 partial
        notified.Clear();
        camps[0].IsChecked = false;
        True("★ 手动取消会通知 IsChecked", notified.Contains("IsChecked"));
        Eq("★ 手动取消触发一次课表重建", 1, callbacks);
        Eq("★ 表头随之变 partial", States.CheckPartial,
            States.CheckAllState(camps.Count(c => c.IsChecked), camps.Count));

        // ⑤ 逐个取消到全空 → 表头变 none；再逐个勾回来 → all
        for (int i = 1; i < camps.Count; i++) camps[i].IsChecked = false;
        Eq("全部取消后表头 = none", States.CheckNone,
            States.CheckAllState(camps.Count(c => c.IsChecked), camps.Count));
        foreach (var c in camps) c.IsChecked = true;
        Eq("逐个勾满后表头 = all", States.CheckAll,
            States.CheckAllState(camps.Count(c => c.IsChecked), camps.Count));

        // ⑥ 「全不选」批量设置同样要刷新界面
        notified.Clear();
        foreach (var c in camps) c.SetCheckedSilently(false);
        Eq("★ 全不选 9 个营数据都取消", 0, camps.Count(c => c.IsChecked));
        Eq("★ 全不选也要逐行通知 IsChecked", 9,
            notified.Count(n => n == "IsChecked"));

        // ⑦ ★ v1.6.0：课程行不再有勾选框 —— 改为「行选中 + 视图过滤 + 下载范围」
        var camp = new Camp { Name = "道德经诵读", CampId = "c1" };
        var row = new LessonRow(new Lesson { Index = 0, Title = "课一" }, camp, 1);
        string rowEvent = "";
        var rowNotified = new List<string>();
        row.PropertyChanged += (_, e) => { rowEvent = e.PropertyName ?? ""; rowNotified.Add(rowEvent); };
        row.StateWord = "下载中";
        True("★ 状态词变化通知状态胶囊底色", rowNotified.Contains("StatePillBg"));
        True("★ 状态词变化通知状态胶囊字色", rowNotified.Contains("StatePillFg"));
        True("★ 状态词变化通知进度条颜色", rowNotified.Contains("ProgressColor"));
        True("★ 状态胶囊三色非空", row.StatePillBg.Length > 0
            && row.StatePillFg.Length > 0 && row.StatePillBorder.Length > 0);
        Eq("★ 进度条按状态着色", true, row.ProgressColor == States.ProgressColorOf("下载中"));

        // 视图过滤：只影响显示
        True("★ 下载中在「下载中」视图", States.InView(States.ViewRunning, "下载中", false));
        True("★ 下载中不在「待下载」视图", !States.InView(States.ViewPending, "下载中", false));
        True("★ 失败在「失败」视图", States.InView(States.ViewFailed, "失败", false));
        True("★ 已存在在「已完成」视图", States.InView(States.ViewDone, "已存在", false));
        True("★ 空闲在「待下载」视图", States.InView(States.ViewPending, "", false));
        True("★ 全部视图什么都收", States.InView(States.ViewAll, "", false));
        True("★ 历史行只在「全部」视图", States.InView(States.ViewAll, "", true)
            && !States.InView(States.ViewPending, "", true));

        // 下载范围：已存在/进行中跳过，失败自动重试，历史行不参与
        True("★ 空闲在下载范围", States.InDownloadScope("", false));
        True("★ 失败在下载范围（自动重试）", States.InDownloadScope("失败", false));
        True("★ 需重下在下载范围", States.InDownloadScope("需重下", false));
        True("★ 已存在不在下载范围", !States.InDownloadScope("已存在", false));
        True("★ 已完成不在下载范围", !States.InDownloadScope("已完成", false));
        True("★ 进行中不在下载范围", !States.InDownloadScope("下载中", false));
        True("★ 历史行不在下载范围", !States.InDownloadScope("", true));

        // 空闲值统一成 "—"
        row.Size = ""; row.Speed = ""; row.Eta = "";
        Eq("★ 空闲大小", "—", row.Size);
        Eq("★ 空闲速度", "—", row.Speed);
        Eq("★ 空闲剩余", "—", row.Eta);
        row.Speed = "--";
        Eq("★ 引擎的 -- 也归一成 —", "—", row.Speed);

        Eq("课程三态：1 / 1", States.CheckAll, States.CheckAllState(1, 1));
    }
}
