using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;

namespace Xqd.Core;

/// <summary>
/// 文件名规范 —— 唯一事实来源。
/// 对应 xqd_platform.safe_name / lesson_stem / expected_ext / course_filename
/// 与 xqd_api.course_filename（Server/CLI 用的旧签名兼容版）。
/// </summary>
public static class Naming
{
    // 只替换 ASCII 非法字符；全角冒号「：」必须保留。
    private static readonly Regex Illegal = new(@"[\\/:*?""<>|\r\n\t]", RegexOptions.Compiled);
    private static readonly HashSet<string> Reserved = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    };

    public static string SafeName(string name)
    {
        if (string.IsNullOrEmpty(name)) return "未命名";
        var s = Illegal.Replace(name, "_").Trim().TrimEnd('.');
        if (Reserved.Contains(s)) s = "_" + s;
        return string.IsNullOrEmpty(s) ? "未命名" : s;
    }

    /// <summary>startTime 毫秒 → YYYY.MM.DD（本地时区，与 Python fromtimestamp 一致）。</summary>
    public static string FmtDate(long ms)
    {
        if (ms <= 0) return "";
        try
        {
            return DateTimeOffset.FromUnixTimeMilliseconds(ms)
                .ToLocalTime().ToString("yyyy.MM.dd", CultureInfo.InvariantCulture);
        }
        catch { return ""; }
    }

    /// <summary>startTime 毫秒 → MM.DD HH:MM（App 卡片显示格式）。</summary>
    public static string FmtWhen(long ms)
    {
        if (ms <= 0) return "";
        try
        {
            return DateTimeOffset.FromUnixTimeMilliseconds(ms)
                .ToLocalTime().ToString("MM.dd HH:mm", CultureInfo.InvariantCulture);
        }
        catch { return ""; }
    }

    /// <summary>成品文件主名：&lt;序号&gt;.&lt;课名&gt;.&lt;日期&gt;（不含扩展名）。</summary>
    public static string LessonStem(Lesson lesson)
    {
        var parts = new List<string> { $"{lesson.Seq}.{SafeName(lesson.Title)}" };
        if (!string.IsNullOrEmpty(lesson.WhenDate)) parts.Add(lesson.WhenDate);
        return string.Join(".", parts);
    }

    /// <summary>AUDIO 保持原始音频容器，其余统一 MP4。</summary>
    public static string ExpectedExt(Lesson lesson) =>
        string.Equals(lesson.Type, "AUDIO", StringComparison.OrdinalIgnoreCase) ? ".mp3" : ".mp4";

    /// <summary>
    /// 成品文件名：&lt;序号&gt;.&lt;课名&gt;.&lt;日期&gt;.&lt;扩展名&gt;。
    /// ★ 不产生 -1 / -2 重名后缀：重名时正确做法是「已有完整成品→跳过；残件→删掉覆盖重下」。
    /// </summary>
    public static string CourseFilename(Lesson lesson, string ext = null) =>
        LessonStem(lesson) + (ext ?? ExpectedExt(lesson));

    /// <summary>xqd_api.course_filename 的兼容版（营内已用名去重，追加 -1/-2）。</summary>
    public static string CourseFilenameApi(string title, int seq, string date,
                                           HashSet<string> used = null)
    {
        var bas = $"{seq}.{SafeName(title)}";
        if (!string.IsNullOrEmpty(date)) bas += "." + date;
        var name = bas + ".mp4";
        if (used != null)
        {
            var k = 1;
            while (used.Contains(name.ToLowerInvariant()))
                name = $"{bas}-{k++}.mp4";
            used.Add(name.ToLowerInvariant());
        }
        return name;
    }

    /// <summary>营目录名（下载与已下载检测必须用同一个，否则扫描永远找不到）。</summary>
    public static string CampFolder(string campName) => SafeName(campName);

    /// <summary>
    /// ffmpeg 临时输出 —— 必须以 .mp4 结尾（.part 结尾会让 ffmpeg 认不出封装格式）。
    /// 与 xqd_app._ff_out_path 一致：去掉原 .mp4 后加 ".part.mp4"。
    /// </summary>
    public static string TempPartPath(string outPath)
    {
        var dir = Path.GetDirectoryName(outPath) ?? "";
        var name = Path.GetFileName(outPath);
        var stem = name.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase)
            ? name.Substring(0, name.Length - 4) : name;
        return Path.Combine(dir, stem + ".part.mp4");
    }
}
