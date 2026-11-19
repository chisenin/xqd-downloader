using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Xqd.Avalonia.Views;

namespace Xqd.Avalonia;

public sealed partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            if (Program.WaitAuthMode)
            {
                // --waitauth：只开等待窗，关掉就退出（不加载主界面）
                desktop.MainWindow = new WaitAuthWindow(Program.WaitAuthTimeoutSec);
                desktop.ShutdownMode = ShutdownMode.OnMainWindowClose;
            }
            else
            {
                desktop.MainWindow = new MainWindow();
                desktop.ShutdownMode = ShutdownMode.OnMainWindowClose;
            }
        }
        base.OnFrameworkInitializationCompleted();
    }
}
