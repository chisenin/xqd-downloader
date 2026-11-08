using System;
using System.Threading;
using Xqd.Core;
using Xqd.Gui.Controls;

namespace Xqd.Gui.ViewModels;

/// <summary>
/// 一次下载任务的运行期状态（对应 xqd_gui 里的 job dict）。
/// ★ 两个独立速率计：Bmeter（字节→速度列 / 直链音频 ETA）、Meter（内容时长→分片视频 ETA）。
/// </summary>
public sealed class Job
{
    public int JobId { get; set; }
    public Lesson Lesson { get; set; }
    public Camp Camp { get; set; }
    public string OutPath { get; set; } = "";
    public string Quality { get; set; } = "max";
    public string SegDir { get; set; } = "";

    // 进度跟踪
    public long Down { get; set; }
    public long Total { get; set; }
    public double DoneDur { get; set; }
    public double TotalDur { get; set; }
    public string Unit { get; set; } = "dur";        // dur | byte
    public double Speed { get; set; }                // 字节速率 B/s
    public double RateDur { get; set; }              // 内容速率 秒/秒
    public double? Eta { get; set; }
    public double EtaFixed { get; set; }             // 封装/校验阶段的一次性估算
    public string Phase { get; set; } = "";
    public bool Finished { get; set; }
    public double T0 { get; set; }                   // 真正开跑时刻（算用时）

    public long CachedBytes { get; set; }
    public int CachedSegs { get; set; }

    public SpeedMeter Bmeter { get; } = new SpeedMeter();
    public SpeedMeter Meter { get; } = new SpeedMeter();

    // ★ v1.6.0：原来的 TaskRow 引用已删除 —— 合并单表后任务状态直接写回课程行。
    public CancellationTokenSource Cts { get; } = new CancellationTokenSource();

    /// <summary>按当前量纲算百分比（分片视频用时长，直链音频用字节）。</summary>
    public int Percent()
    {
        if (Finished) return 100;
        if (Unit == "dur" && TotalDur > 0)
            return (int)Math.Max(0, Math.Min(100, DoneDur * 100.0 / TotalDur));
        if (Total > 0)
            return (int)Math.Max(0, Math.Min(100, Down * 100.0 / Total));
        return 0;
    }
}
