using System;
using System.Collections.Generic;

namespace Xqd.Gui.Controls;

/// <summary>
/// 速率计：最近 8 秒滑动窗口算「任意单调递增量」的速率。
/// 喂字节得到 B/s（速度列 / 直链音频 ETA），喂内容时长得到倍速（分片视频 ETA）。
/// 与 xqd_gui.SpeedMeter 逐行对照：>6 秒无新进度速率归零，last_speed 保留暂停前有效值。
/// </summary>
public sealed class SpeedMeter
{
    private readonly double _window;
    private readonly List<Sample> _samples = new();

    private readonly struct Sample
    {
        public Sample(double t, double v) { T = t; V = v; }
        public double T { get; }
        public double V { get; }
    }

    public SpeedMeter(double window = 8.0) { _window = window; }

    /// <summary>最近一次累计值。</summary>
    public double Last { get; private set; }

    /// <summary>最近一次有效速率（暂停 / 速率暂不可测时兜底用）。</summary>
    public double LastSpeed { get; private set; }

    public void Reset(double value = 0)
    {
        _samples.Clear();
        Last = value;
        LastSpeed = 0.0;
    }

    public void Add(double value, double? now = null)
    {
        double t = now ?? Now();
        Last = value;
        _samples.Add(new Sample(t, value));
        double cut = t - _window;
        while (_samples.Count > 2 && _samples[0].T < cut)
            _samples.RemoveAt(0);
        double sp = CalcSpeed(t);
        if (sp > 0) LastSpeed = sp;
    }

    public double Speed(double? now = null) => CalcSpeed(now ?? Now());

    private double CalcSpeed(double now)
    {
        if (_samples.Count < 2) return 0.0;
        // 数据过期（例如卡在封装/校验）不再报速率，避免显示假的「还在很快地下」
        if (now - _samples[_samples.Count - 1].T > 6.0) return 0.0;
        var a = _samples[0];
        var b = _samples[_samples.Count - 1];
        double dt = b.T - a.T;
        if (dt <= 0.2) return 0.0;
        return Math.Max(0.0, (b.V - a.V) / dt);
    }

    private static double Now() =>
        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
}
