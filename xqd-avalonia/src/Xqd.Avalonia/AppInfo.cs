using System.Reflection;

namespace Xqd.Avalonia;

/// <summary>版本与运行环境的单一出口（关于窗 / 状态栏共用）。</summary>
public static class AppInfo
{
    public static string Version
    {
        get
        {
            var v = Assembly.GetExecutingAssembly().GetName().Version;
            return v == null ? "1.7.0" : $"{v.Major}.{v.Minor}.{v.Build}";
        }
    }

    public static string RuntimeInfo =>
        $"运行于 .NET {System.Environment.Version.Major}.{System.Environment.Version.Minor}"
        + $" · {System.Runtime.InteropServices.RuntimeInformation.OSDescription}";
}
