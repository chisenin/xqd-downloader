using System;
using System.Collections.Generic;

namespace Xqd.Core;

/// <summary>一个营（课程集合）。对应 Python 的 xqd_platform.Camp。</summary>
public sealed class Camp
{
    public string Name { get; set; } = "";
    public string CampId { get; set; } = "";
    public string Kind { get; set; } = "";
    public int Count { get; set; }
    public string Badge { get; set; } = "";
    public string PeriodId { get; set; } = "";
    public string SkuType { get; set; } = "";
    public string BusinessType { get; set; } = "";
    public string BusinessId { get; set; } = "";

    public override string ToString() => $"<Camp {Name} ({Count}节)>";
}

/// <summary>一节课。对应 Python 的 xqd_platform.Lesson。</summary>
public sealed class Lesson
{
    /// <summary>营内课表顺序，0 起。成品文件名里的序号 = Index + 1。</summary>
    public int Index { get; set; }
    public string Title { get; set; } = "";
    /// <summary>MM.DD HH:MM，与 App 课程卡片一致。</summary>
    public string When { get; set; } = "";
    /// <summary>YYYY.MM.DD，成品文件名里的标题后缀。</summary>
    public string WhenDate { get; set; } = "";
    public double Duration { get; set; }
    /// <summary>VIDEO / INTELLIGENT_LIVE / AUDIO / OPEN_COURSE。</summary>
    public string Type { get; set; } = "";
    public string TopicId { get; set; } = "";
    public string RoomId { get; set; } = "";
    public string FileId { get; set; } = "";
    public string CampName { get; set; } = "";

    // ---- 运行期状态（不参与 API 序列化）----
    public double Progress { get; set; }
    /// <summary>idle | queued | running | done | failed | skipped</summary>
    public string State { get; set; } = "idle";
    public string Message { get; set; } = "";
    public string OutPath { get; set; } = "";
    /// <summary>界面状态词（中文），如「下载中」「已完成」。</summary>
    public string StateWord { get; set; } = "";
    /// <summary>所属营对象引用（多营合并时必须逐行绑定，不能按合并行号重排）。</summary>
    public Camp CampOfRow { get; set; }

    public int Seq => Index + 1;
    public string Key => CampName + "|" + Index;
    public string Display => $"[{Seq:00}] {Title}";
    public override string ToString() => $"<Lesson {Index} {Title}>";
}

/// <summary>数据源模式：api（默认，不需要模拟器）/ adb（旧路径）。</summary>
public enum DataSourceMode { Api, Adb }

/// <summary>下载进度快照。对应引擎的 on_progress 回调参数。</summary>
public sealed class ProgressInfo
{
    public double DoneDuration { get; set; }
    public double TotalDuration { get; set; }
    public long DoneBytes { get; set; }
    public long TotalBytes { get; set; }
    /// <summary>"dur"（分片视频，用内容时长算进度）/ "byte"（直链音频）。</summary>
    public string Unit { get; set; } = "dur";
    public int Percent => TotalDuration > 0
        ? (int)Math.Max(0, Math.Min(100, DoneDuration * 100.0 / TotalDuration))
        : (TotalBytes > 0 ? (int)Math.Max(0, Math.Min(100, DoneBytes * 100.0 / TotalBytes)) : 0);
}

/// <summary>一次下载请求。GUI / Server / CLI 三种前端共用。</summary>
public sealed class DownloadRequest
{
    public Camp Camp { get; set; }
    public Lesson Lesson { get; set; }
    public string OutPath { get; set; } = "";
    public string Quality { get; set; } = "max";
    public int SegmentWorkers { get; set; } = States.SegmentWorkers;

    /// <summary>调用方已解析好的播放地址；为空时引擎通过 DataSource 现场解析。</summary>
    public string PlayUrl { get; set; } = "";
    /// <summary>调用方持有的已授权数据源（GUI / Server / CLI 复用同一个实例）。</summary>
    public IDataSource DataSource { get; set; }
    /// <summary>持久分片缓存目录；为空时引擎按成品路径派生。</summary>
    public string SegDir { get; set; } = "";
    /// <summary>true = 成功后也保留分片（调试用）。默认成功即清、失败必留。</summary>
    public bool KeepParts { get; set; }
}

/// <summary>下载结果。</summary>
public sealed class DownloadResult
{
    public bool Ok { get; set; }
    public string Message { get; set; } = "";
    public string OutPath { get; set; } = "";
    public long Size { get; set; }
    public double Duration { get; set; }
}
