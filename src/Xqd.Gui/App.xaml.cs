using System;
using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Threading;
using Xqd.Core;

namespace Xqd.Gui;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += OnUnhandled;
        base.OnStartup(e);
    }

    private void OnUnhandled(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        // 界面异常不直接崩掉主窗口；尽量留一份诊断文本。
        try
        {
            var dir = Config.ToolDir;
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "gui-error.log"),
                "[" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "] " + e.Exception + Environment.NewLine,
                new UTF8Encoding(false));
        }
        catch { /* ignore */ }
        e.Handled = true;
    }
}
