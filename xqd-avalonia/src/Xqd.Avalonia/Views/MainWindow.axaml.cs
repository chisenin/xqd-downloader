using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Rendering;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Xqd.Avalonia.Controls;
using Xqd.Core;
using Xqd.Core.Auth;
using Xqd.Core.Setup;
using Xqd.Core.Ui;

namespace Xqd.Avalonia.Views;

/// <summary>
/// 主窗口 —— 单表 8 列 + 左营列表 + 日志。
///
/// 设计原则（与 WPF 版一致，换 UI 框架不改行为）：
///  · 一个课表只出现一次：勾营 → 课表并入同一张表；不再有"课程表 / 下载管理"两张表。
///  · 下载范围只看**状态词**：待下载 + 失败/需重下；已完成/已存在/进行中一律跳过。
///  · 进度刷新限流 10 次/秒：分片多时把 UI 线程灌满会拖不动窗口。
///  · 历史行的唯一作用是"让你记得下过什么"，不参与下载、不可点下载。
/// </summary>
public partial class MainWindow : Window
{
    // ── 单表列宽（必须与 XAML 表头一致；标题列由窗口宽度算） ──
    private const double WState = 92, WCamp = 120, WDur = 66, WSize = 112,
                         WSpeed = 78, WEta = 78, WProg = 150;

    public static readonly StyledProperty<double> TitleWidthProperty =
        AvaloniaProperty.Register<MainWindow, double>(nameof(TitleWidth), 280);

    public static readonly StyledProperty<bool> ShowCampColumnProperty =
        AvaloniaProperty.Register<MainWindow, bool>(nameof(ShowCampColumn), true);

    public double TitleWidth
    {
        get => GetValue(TitleWidthProperty);
        set => SetValue(TitleWidthProperty, value);
    }

    public bool ShowCampColumn
    {
        get => GetValue(ShowCampColumnProperty);
        set => SetValue(ShowCampColumnProperty, value);
    }

    // ── 数据 ──
    private AppConfig _cfg = new();
    private IDataSource _ds;
    private IPlatform _platform;
    private string _cookie = "";
    private string _viewTag = States.ViewAll;
    private IExistingChecker _checker;
    private string _outRoot = "";

    private readonly List<Camp> _camps = new();
    private readonly Dictionary<string, List<Lesson>> _campLessons = new();
    private readonly ObservableCollection<CampRowVm> _campRows = new();
    private readonly ObservableCollection<LessonRow> _rows = new();      // 全部行
    private readonly ObservableCollection<LessonRow> _view = new();      // 当前视图
    private readonly List<HistoryRecord> _hist = new();
    private readonly ObservableCollection<HistVm> _histVm = new();

    // ── 下载 ──
    private readonly Queue<LessonRow> _queue = new();
    private readonly List<DownloadControl> _controls = new();
    private CancellationTokenSource _runCts;
    private CancellationTokenSource _uiCts = new();
    private int _active;
    private bool _running;
    private bool _paused;
    private int _jobSeq;
    private long _runStartTicks;

    // ── 窗口拖动 ──
    private bool _dragging;
    private bool _dragMoved;
    private bool _pressOnBrand;
    private PixelPoint _dragStartScreen;
    private PixelPoint _dragOriginPos;
    private IPointer _captured;

    private LessonRow _ctxRow;
    private DispatcherTimer _bannerTimer;

    public MainWindow()
    {
        InitializeComponent();

        LstCamps.ItemsSource = _campRows;
        LstRows.ItemsSource = _view;
        LstHist.ItemsSource = _histVm;

        SizeChanged += (_, _) => UpdateTitleWidth();
        Opened += OnOpened;
        KeyDown += OnKeyDown;
        PropertyChanged += OnWinPropertyChanged;
    }

    // ══════════════════════════════════════════════════════ 启动

    private void OnOpened(object sender, EventArgs e)
    {
        _cfg = Config.Load();
        _outRoot = Config.EffectiveOutDir(_cfg);
        EdOut.Text = _outRoot;
        SelectQuality(_cfg.quality);
        ChkAutoLaunch.IsChecked = _cfg.auto_launch;
        ChkAutoClose.IsChecked = _cfg.auto_close;

        LblVersion.Text = $"{States.AppTitle} v{AppInfo.Version}";
        LblStatus.Text = "配置目录：" + Config.ToolDir;
        UpdateTitleWidth();

        LoadHistory();
        Log($"{States.AppTitle} v{AppInfo.Version} 启动");
        Log("配置目录：" + Config.ToolDir);

        _ = AutoStartAsync();
    }

    private async Task AutoStartAsync()
    {
        try
        {
            // 先走本机缓存授权：日常启动不碰模拟器
            if (await EnsureAuthAsync(false))
                await RefreshCampsAsync(quiet: true);
            else
                ShowBanner("尚未授权。请点「重新授权」从 MuMu 模拟器读取兴趣岛登录态。", BannerKind.Info);
        }
        catch (Exception e)
        {
            Log("启动检查失败：" + e.Message);
        }
    }

    // ══════════════════════════════════════════════════════ 授权 / 数据源

    private async Task<bool> EnsureAuthAsync(bool force)
    {
        LblStatus.Text = force ? "正在从 MuMu 读取登录态…" : "正在检查本机授权…";

        // ★ 点了「重新授权」却连 MuMuManager 都找不到时，别只甩一句报错 ——
        //   直接弹文件选择框让用户选一次（选完记住），与 hgvd 的兜底一致。
        if (force && !await EnsureMumuLocatedAsync())
        {
            LblAuth.Text = "未授权";
            ShowBanner("没找到 MuMuManager.exe，已取消选择。可先打开 MuMu，"
                       + "或再点一次「重新授权」手动指定位置。", BannerKind.Err);
            return false;
        }

        var auth = await RunAuthOnceAsync(force);

        // 授权逻辑内部找不到 MuMu 时也兜底：让用户选一次，然后立刻重试（只重试一次）
        if (!auth.Ok && (auth.Message ?? "").Contains("找不到 MuMuManager.exe"))
        {
            if (await PickMumuManagerAsync())
                auth = await RunAuthOnceAsync(force);
        }

        // ★ 模拟器在跑但没登录 / 这台没装 App：不逼用户反复点「重试」，
        //   弹置顶小窗边等边取（每 2 秒扫实例，最多 180 秒），读到就自动继续。
        if (!auth.Ok && NeedsWaitForLogin(auth.Message))
        {
            var win = new WaitAuthWindow(180);
            int idx = await win.ShowDialog<int>(this);
            if (idx >= 0)
            {
                Log($"实例 {idx} 已登录，重新读取授权…");
                auth = await RunAuthOnceAsync(true);
            }
        }

        if (!auth.Ok)
        {
            LblAuth.Text = "未授权";
            if (!string.IsNullOrEmpty(auth.Message)) Log(auth.Message);
            ShowBanner(auth.Message ?? "授权失败", BannerKind.Err);
            return false;
        }

        _cookie = auth.Cookie;
        string mode = _cfg.mode == "adb" ? "adb" : "api";
        _ds = Services.CreateDataSource(
            mode == "adb" ? DataSourceMode.Adb : DataSourceMode.Api, _cookie);
        _platform = _ds as IPlatform;

        LblAuth.Text = auth.FromCache ? "已授权（本机缓存）" : "已授权（模拟器）";
        Log(auth.FromCache
            ? "已使用本机保存的授权（未启动模拟器）"
            : "已从模拟器读取登录态并落盘复用");
        return true;
    }

    private Task<AuthResult> RunAuthOnceAsync(bool force) =>
        Services.Auth.EnsureAuthAsync(
            force, Log,
            ChkAutoLaunch.IsChecked == true,
            ChkAutoClose.IsChecked == true,
            _uiCts.Token);

    /// <summary>MuMu 已能定位就直接过；否则引导用户点选一次 MuMuManager.exe。</summary>
    private async Task<bool> EnsureMumuLocatedAsync()
    {
        try
        {
            if (!string.IsNullOrEmpty(MumuAuth.FindMumu())) return true;
        }
        catch { /* 定位失败 → 走点选 */ }
        return await PickMumuManagerAsync();
    }

    /// <summary>
    /// 这些失败属于「人还没操作完」，适合开等待窗：
    /// App 没登录 / 没读到登录态 / 这台实例没装 App（用户可能正在装）。
    /// </summary>
    private static bool NeedsWaitForLogin(string message)
    {
        if (string.IsNullOrEmpty(message)) return false;
        return message.Contains("App 未登录")
            || message.Contains("未检测到登录态")
            || message.Contains("没有「兴趣岛」App");
    }

    /// <summary>文件选择框选 MuMuManager.exe，选完记进 tools.json（下次不再问）。</summary>
    private async Task<bool> PickMumuManagerAsync()
    {
        try
        {
            var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "选择 MuMuManager.exe（通常在 MuMu 安装目录的 nx_main 里）",
                AllowMultiple = false,
                FileTypeFilter = new[]
                {
                    new FilePickerFileType("MuMuManager.exe")
                    {
                        Patterns = new[] { "MuMuManager.exe" },
                    },
                },
            });
            if (files == null || files.Count == 0) return false;
            string path = files[0].TryGetLocalPath() ?? "";
            if (path.Length == 0) return false;
            if (!ToolLocator.RememberMumuManager(path))
            {
                ShowBanner("选中的不是 MuMuManager.exe：" + path, BannerKind.Err);
                return false;
            }
            Log("已记住 MuMu 位置：" + path);
            return true;
        }
        catch (Exception e)
        {
            Log("选择 MuMu 位置失败：" + e.Message);
            return false;
        }
    }

    private async void BtnAuth_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            bool ok = await EnsureAuthAsync(true);
            if (ok)
            {
                ShowBanner("授权成功。", BannerKind.Ok);
                await RefreshCampsAsync();
            }
        }
        catch (Exception ex)
        {
            Log("授权失败：" + ex.Message);
            ShowBanner("授权失败：" + ex.Message, BannerKind.Err);
        }
        finally { LblStatus.Text = "就绪"; }
    }

    // ══════════════════════════════════════════════════════ 营列表

    private async Task RefreshCampsAsync(bool quiet = false)
    {
        if (_ds == null) return;
        if (!quiet) LblStatus.Text = "正在拉取营列表…";
        try
        {
            var camps = await _ds.ListCampsAsync("全部", _uiCts.Token);
            _camps.Clear();
            _camps.AddRange(camps);
            BuildCampRows();
            Log($"营列表已更新：{_camps.Count} 个营"
                + $"（已购 {_camps.Count(c => c.SkuType != "OPEN_COURSE")} / "
                + $"公开课 {_camps.Count(c => c.SkuType == "OPEN_COURSE")}）");
            if (!quiet) ShowBanner($"已载入 {_camps.Count} 个营，勾选即把课表并入右侧。", BannerKind.Ok);
        }
        catch (Exception ex)
        {
            Log("拉取营列表失败：" + ex.Message);
            ShowBanner("拉取营列表失败：" + ex.Message
                     + "\n若是登录态过期，请点「重新授权」。", BannerKind.Err);
        }
        finally { LblStatus.Text = "就绪"; }
    }

    private void BuildCampRows()
    {
        string filter = (EdCampSearch.Text ?? "").Trim();
        // 记住已勾选的营（按 Key 认，重建后恢复）
        var checkedKeys = _campRows.Where(r => !r.IsHeader && r.Item.IsChecked)
                                   .Select(r => r.Item.Key).ToHashSet();

        _campRows.Clear();
        var groups = new (string Title, Func<Camp, bool> Match)[]
        {
            ("已购课程", c => c.SkuType != "OPEN_COURSE"),
            ("公开课", c => c.SkuType == "OPEN_COURSE"),
        };

        foreach (var g in groups)
        {
            var items = _camps.Where(g.Match)
                              .Where(c => filter.Length == 0 || c.Name.Contains(filter, StringComparison.OrdinalIgnoreCase))
                              .ToList();
            if (items.Count == 0) continue;

            _campRows.Add(new CampRowVm
            {
                IsHeader = true,
                Header = g.Title,
                HeaderCount = $"{items.Count} 个",
            });

            // 同名营编号（第 2 个起显示 "(2)"）
            var seen = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (var c in items)
            {
                int seq = seen.TryGetValue(c.Name, out var n) ? n + 1 : 1;
                seen[c.Name] = seq;

                var item = new CampItem(c, seq);
                if (checkedKeys.Contains(item.Key)) item.SetCheckedSilently(true);
                item.CheckChanged = OnCampChecked;
                _campRows.Add(new CampRowVm { Item = item });
            }
        }

        LblCampCount.Text = $"{_camps.Count} 个营";
        UpdateCheckAllState();
    }

    private void EdCampSearch_TextChanged(object sender, TextChangedEventArgs e) => BuildCampRows();

    private void CampRow_PointerPressed(object sender, PointerPressedEventArgs e)
    {
        if (sender is not Border b || b.DataContext is not CampRowVm vm || vm.IsHeader) return;
        if (vm.Item == null) return;

        // 点在复选框上就交给复选框自己（它已经双向绑定）
        var src = e.Source as Visual;
        while (src != null && src != b)
        {
            if (src is CheckBox) return;
            src = src.GetVisualParent();
        }

        vm.Item.IsChecked = !vm.Item.IsChecked;
        LstCamps.Selection.Clear();
        e.Handled = true;
    }

    private void OnCampChecked(CampItem item)
    {
        UpdateCheckAllState();
        _ = ApplyCampAsync(item);
    }

    private async Task ApplyCampAsync(CampItem item)
    {
        if (item == null) return;
        if (!item.IsChecked)
        {
            RemoveCampRows(item);
            RebuildView();
            UpdateSummary();
            return;
        }
        try
        {
            if (_ds == null)
            {
                ShowBanner("尚未授权，无法取课表。", BannerKind.Err);
                return;
            }
            if (!_campLessons.TryGetValue(item.Key, out var lessons))
            {
                LblStatus.Text = $"正在取「{item.Display}」课表…";
                lessons = await _ds.CampCatalogAsync(item.Camp, _uiCts.Token);
                _campLessons[item.Key] = lessons;
                Log($"「{item.Display}」课表 {lessons.Count} 节");
            }
            AddCampRows(item, lessons);
            RebuildView();
            UpdateSummary();
        }
        catch (Exception ex)
        {
            Log($"取「{item.Display}」课表失败：{ex.Message}");
            ShowBanner($"取「{item.Display}」课表失败：{ex.Message}", BannerKind.Err);
        }
        finally { LblStatus.Text = "就绪"; }
    }

    private void AddCampRows(CampItem item, List<Lesson> lessons)
    {
        RemoveCampRows(item);
        string campName = item.Camp.Name;
        int seqBase = 0;
        foreach (var l in lessons)
        {
            var row = new LessonRow(l, item.Camp, l.Index + 1);
            row.ShowCampColumn = true;

            // 已成品判定：文件名主键 + 10KB 门槛 + ffprobe 时长容差
            var state = _checker?.Check(campName, Naming.LessonStem(l), l.Duration);
            if (state != null && state.IsOk)
            {
                row.StateWord = "已存在";
                row.Progress = 100;
                row.Size = LessonRow.FmtSize(state.Size);
                row.OutPath = state.Path;
            }
            _rows.Add(row);
            seqBase++;
        }
    }

    private void RemoveCampRows(CampItem item)
    {
        for (int i = _rows.Count - 1; i >= 0; i--)
        {
            var r = _rows[i];
            if (r.IsHistory) continue;
            if (r.CampOfRow?.Name == item.Camp.Name) _rows.RemoveAt(i);
        }
        _campLessons.Remove(item.Key);
    }

    private void ChkAll_Click(object sender, RoutedEventArgs e)
    {
        bool want = ChkAll.IsChecked != false;   // null / true 都当"全选"
        ChkAll.IsChecked = want;                 // 二态化，避免卡在 null

        foreach (var r in _campRows)
            if (!r.IsHeader && r.Item != null)
                r.Item.SetCheckedSilently(want);

        // 一次性同步：并课表 / 清空，避免逐营触发几十次重建
        _ = SyncAllCheckedAsync(want);
    }

    private async Task SyncAllCheckedAsync(bool want)
    {
        if (!want)
        {
            _rows.Clear();
            _campLessons.Clear();
            AppendHistoryRows();
            RebuildView();
            UpdateSummary();
            return;
        }
        if (_ds == null)
        {
            ShowBanner("尚未授权，无法取课表。", BannerKind.Err);
            return;
        }

        var targets = _campRows.Where(r => !r.IsHeader && r.Item?.IsChecked == true)
                               .Select(r => r.Item).ToList();
        LblStatus.Text = $"正在取 {targets.Count} 个营的课表…";
        int done = 0;
        foreach (var item in targets)
        {
            try
            {
                if (!_campLessons.TryGetValue(item.Key, out var lessons))
                {
                    lessons = await _ds.CampCatalogAsync(item.Camp, _uiCts.Token);
                    _campLessons[item.Key] = lessons;
                }
                AddCampRows(item, lessons);
            }
            catch (Exception ex)
            {
                Log($"取「{item.Display}」课表失败：{ex.Message}");
            }
            done++;
            LblStatus.Text = $"正在取课表… {done}/{targets.Count}";
        }
        AppendHistoryRows();
        RebuildView();
        UpdateSummary();
        LblStatus.Text = "就绪";
        Log($"已并入 {targets.Count} 个营的课表，共 {_rows.Count(r => !r.IsHistory)} 节");
    }

    private void UpdateCheckAllState()
    {
        var items = _campRows.Where(r => !r.IsHeader && r.Item != null).Select(r => r.Item).ToList();
        int n = items.Count;
        int k = items.Count(i => i.IsChecked);
        ChkAll.IsChecked = n <= 0 || k <= 0 ? false
                        : (k >= n ? true : (bool?)null);
        LblCampHint.Text = n == 0
            ? "还没有营列表：点「刷新」拉取，或先「重新授权」"
            : $"共 {n} 个营，已勾选 {k} 个 · 勾选即并入右侧课表";
    }

    private void BtnRefresh_Click(object sender, RoutedEventArgs e) => _ = RefreshCampsAsync();

    // ══════════════════════════════════════════════════════ 视图 / 表格

    private void View_Checked(object sender, RoutedEventArgs e)
    {
        if (sender is not RadioButton rb) return;
        _viewTag = rb.Tag as string ?? States.ViewAll;
        RebuildView();
        UpdateSummary();
    }

    private void RebuildView()
    {
        var selected = LstRows.SelectedItems?.Cast<LessonRow>().ToList() ?? new List<LessonRow>();
        _view.Clear();
        foreach (var r in _rows)
        {
            if (!States.InView(_viewTag, r.StateWord, r.IsHistory)) continue;
            if (!MatchesRowSearch(r)) continue;
            _view.Add(r);
        }
        // 恢复选中（行对象没变，直接按引用选）
        if (selected.Count > 0)
        {
            LstRows.Selection.Clear();
            foreach (var r in selected)
            {
                int idx = _view.IndexOf(r);
                if (idx >= 0) LstRows.Selection.Select(idx);
            }
        }
        UpdateCampColumn();
    }

    private bool MatchesRowSearch(LessonRow r)
    {
        string q = (EdCampSearch.Text ?? "").Trim();
        if (q.Length == 0) return true;
        // 左栏搜索只筛营名；右侧表格保持完整（避免两个搜索框互相干扰）
        return true;
    }

    private void UpdateCampColumn()
    {
        var camps = _rows.Where(r => !r.IsHistory).Select(r => r.CampOfRow?.Name).Distinct().Count();
        bool show = camps > 1;
        if (ShowCampColumn != show)
        {
            ShowCampColumn = show;
            HdrCamp.IsVisible = show;
            UpdateTitleWidth();
        }
    }

    private void UpdateTitleWidth()
    {
        double avail = LstRows?.Bounds.Width ?? 0;
        if (avail <= 0) return;
        double fixedW = WState + WDur + WSize + WSpeed + WEta + WProg + (ShowCampColumn ? WCamp : 0);
        double w = avail - fixedW - 26;      // 26：左右内边距 + 滚动条
        TitleWidth = Math.Max(160, w);
    }

    // ══════════════════════════════════════════════════════ 行交互

    private void Row_PointerPressed(object sender, PointerPressedEventArgs e)
    {
        if (sender is not Border b || b.DataContext is not LessonRow row) return;
        _ctxRow = row;

        if (e.GetCurrentPoint(b).Properties.IsRightButtonPressed)
        {
            e.Handled = false;   // 交给 ContextFlyout 弹出菜单
            return;
        }
        if (e.ClickCount >= 2)
        {
            if (row.IsHistory)
            {
                OpenFolderOf(row.OutPath);
                return;
            }
            StartDownload(new List<LessonRow> { row });
            e.Handled = true;
        }
    }

    private void MenuDownload_Click(object sender, RoutedEventArgs e)
    {
        var row = _ctxRow;
        if (row == null || row.IsHistory) return;
        StartDownload(new List<LessonRow> { row });
    }

    private async void MenuRetry_Click(object sender, RoutedEventArgs e)
    {
        var row = _ctxRow;
        if (row == null || row.IsHistory) return;
        // 清掉这节的分片缓存与历史状态，再排队
        var outPath = OutPathOf(row);
        try
        {
            Services.History.PurgeParts(outPath, _outRoot);
            RemoveHistoryOf(outPath);
            row.StateWord = "";
            row.Progress = 0;
            row.Size = States.EmptyDash;
            RebuildView();
            Log("已清除分片缓存与历史状态：" + row.Title);
        }
        catch (Exception ex)
        {
            Log("清缓存失败：" + ex.Message);
        }
        StartDownload(new List<LessonRow> { row });
        await Task.CompletedTask;
    }

    private async void MenuCopy_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var clip = TopLevel.GetTopLevel(this)?.Clipboard;
            if (clip != null) await clip.SetTextAsync(_ctxRow?.Title ?? "");
            ShowBanner("课名已复制。", BannerKind.Ok);
        }
        catch (Exception ex) { Log("复制失败：" + ex.Message); }
    }

    private void MenuOpenFolder_Click(object sender, RoutedEventArgs e)
    {
        var row = _ctxRow;
        string path = row?.OutPath;
        if (string.IsNullOrEmpty(path)) path = row == null ? "" : OutPathOf(row);
        OpenFolderOf(path);
    }

    private async void MenuDelete_Click(object sender, RoutedEventArgs e)
    {
        var row = _ctxRow;
        if (row == null) return;
        string path = !string.IsNullOrEmpty(row.OutPath) ? row.OutPath : OutPathOf(row);
        if (!File.Exists(path)) { ShowBanner("文件不存在：" + path, BannerKind.Err); return; }

        bool ok = await MsgBox.ConfirmAsync(this, "删除成品",
            "把该文件移到同目录的 _已删除 文件夹？\n\n" + Path.GetFileName(path), "删除", "取消");
        if (!ok) return;
        try
        {
            string dir = Path.Combine(Path.GetDirectoryName(path) ?? "", "_已删除");
            Directory.CreateDirectory(dir);
            string target = Path.Combine(dir, Path.GetFileName(path));
            if (File.Exists(target)) File.Delete(target);
            File.Move(path, target);
            Log($"已移入 _已删除：{Path.GetFileName(path)}");

            row.StateWord = "";
            row.Progress = 0;
            row.Size = States.EmptyDash;
            row.OutPath = "";
            RemoveHistoryOf(path);
            SaveHistory();
            RebuildView();
            UpdateSummary();
            ShowBanner("已删除成品（可在 _已删除 里找回）。", BannerKind.Ok);
        }
        catch (Exception ex)
        {
            Log("删除失败：" + ex.Message);
            ShowBanner("删除失败：" + ex.Message, BannerKind.Err);
        }
    }

    private void Hist_PointerPressed(object sender, PointerPressedEventArgs e)
    {
        if (sender is not Border b || b.DataContext is not HistVm vm) return;
        if (e.ClickCount >= 2) OpenFolderOf(vm.Path);
    }

    private static void OpenFolderOf(string filePath)
    {
        try
        {
            string dir = File.Exists(filePath)
                ? Path.GetDirectoryName(filePath)
                : (Directory.Exists(filePath) ? filePath : "");
            if (string.IsNullOrEmpty(dir)) return;
            Process.Start(new ProcessStartInfo
            {
                FileName = dir,
                UseShellExecute = true,
            });
        }
        catch { /* 打不开就算了 */ }
    }

    // ══════════════════════════════════════════════════════ 下载

    private string GetQuality()
    {
        if (CmbQuality.SelectedItem is ComboBoxItem item && item.Tag is string q) return q;
        return _cfg.quality ?? "max";
    }

    private void SelectQuality(string q)
    {
        var items = CmbQuality.Items?.Cast<ComboBoxItem>().ToList() ?? new List<ComboBoxItem>();
        int idx = items.FindIndex(i => (i.Tag as string) == (q ?? "max"));
        CmbQuality.SelectedIndex = idx >= 0 ? idx : 0;
    }

    private void CmbQuality_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_cfg == null) return;
        _cfg.quality = GetQuality();
        Config.Save(_cfg);
        Log("画质切换为 " + GetQuality());
    }

    private string OutPathOf(LessonRow row)
    {
        if (!string.IsNullOrEmpty(row.OutPath)) return row.OutPath;
        var camp = row.CampOfRow;
        var lesson = row.Lesson;
        if (camp == null || lesson == null) return "";
        string root = Config.EffectiveOutDir(_cfg);
        return Path.Combine(root, Naming.CampFolder(camp.Name), Naming.CourseFilename(lesson));
    }

    private void BtnRun_Click(object sender, RoutedEventArgs e)
    {
        if (_running) { ShowBanner("正在下载中，暂停/取消后再改范围。", BannerKind.Info); return; }

        var selected = LstRows.SelectedItems?.Cast<LessonRow>()
                             .Where(r => !r.IsHistory).ToList() ?? new List<LessonRow>();
        var targets = selected.Count > 0
            ? selected
            : _rows.Where(r => States.InDownloadScope(r.StateWord, r.IsHistory)).ToList();

        if (targets.Count == 0)
        {
            ShowBanner("没有待下载的课：先在左边勾选营，或选中要下的行。", BannerKind.Info);
            return;
        }
        if (selected.Count > 0)
            Log($"按选中行下载 {targets.Count} 节");

        StartDownload(targets);
    }

    private void StartDownload(List<LessonRow> targets)
    {
        if (_running || targets.Count == 0) return;
        if (_ds == null)
        {
            ShowBanner("尚未授权，无法解析播放地址。", BannerKind.Err);
            return;
        }
        _cfg.quality = GetQuality();
        Config.Save(_cfg);

        _running = true;
        _paused = false;
        _runStartTicks = Environment.TickCount64;
        _runCts = new CancellationTokenSource();
        BtnRun.IsEnabled = false;
        BtnPause.IsEnabled = true;
        BtnPause.Content = "暂停";

        foreach (var r in targets)
        {
            if (!States.InDownloadScope(r.StateWord, r.IsHistory)) continue;
            r.StateWord = States.WordQueued;
            r.Progress = 0;
            r.Size = States.EmptyDash;
            r.Speed = States.EmptyDash;
            r.Eta = States.EmptyDash;
            _queue.Enqueue(r);
        }
        Log($"开始下载：排队 {_queue.Count} 节，网络槽位 {States.MaxLessonWorkers}");
        PumpQueue();
        RebuildView();
        UpdateSummary();
    }

    private void PumpQueue()
    {
        while (_queue.Count > 0 && _active < States.MaxLessonWorkers)
        {
            var row = _queue.Dequeue();
            _active++;
            _ = RunOneAsync(row);
        }
        if (!_running) return;
        if (_active == 0 && _queue.Count == 0) FinishRun();
    }

    private async Task RunOneAsync(LessonRow row)
    {
        var control = new DownloadControl { Paused = _paused };
        lock (_controls) _controls.Add(control);

        var job = new Job
        {
            JobId = ++_jobSeq,
            Lesson = row.Lesson,
            Camp = row.CampOfRow,
            Quality = GetQuality(),
            OutPath = OutPathOf(row),
            T0 = Environment.TickCount64 / 1000.0,
        };
        row.OutPath = job.OutPath;

        long lastUi = 0;
        var cb = new DownloadCallbacks
        {
            Phase = p => RunUi(() =>
            {
                row.StateWord = States.PhaseWord(p);
                if (p == "封装" || p == "校验") row.Speed = States.EmptyDash;
            }),
            Progress = p =>
            {
                job.Down = p.DoneBytes;
                job.Total = p.TotalBytes;
                job.DoneDur = p.DoneDuration;
                job.TotalDur = p.TotalDuration;
                job.Unit = p.Unit;
                job.Bmeter.Add(p.DoneBytes);
                job.Meter.Add(p.DoneDuration);
                job.Speed = job.Bmeter.Speed();
                job.RateDur = job.Meter.Speed();

                long now = Environment.TickCount64;
                bool last = p.Percent >= 100;
                if (!last && now - lastUi < 100) return;   // 限流 10 次/秒
                lastUi = now;

                double? eta = null;
                if (job.Unit == "byte" && job.Speed > 1 && job.Total > job.Down)
                    eta = (job.Total - job.Down) / job.Speed;
                else if (job.Unit == "dur" && job.RateDur > 0.05 && job.TotalDur > job.DoneDur)
                    eta = (job.TotalDur - job.DoneDur) / job.RateDur;

                RunUi(() =>
                {
                    row.Progress = p.Percent;
                    row.Size = job.Total > 0
                        ? $"{LessonRow.FmtSize(job.Down)}/{LessonRow.FmtSize(job.Total)}"
                        : LessonRow.FmtSize(job.Down);
                    row.Speed = Util.FmtSpeed(job.Speed);
                    row.Eta = eta.HasValue ? Util.FmtClock(eta.Value) : States.EmptyDash;
                    Marq.Text = row.Title;
                });
            },
            Log = m => Log("  " + row.Title + " · " + m),
        };

        var req = new DownloadRequest
        {
            Camp = row.CampOfRow,
            Lesson = row.Lesson,
            OutPath = job.OutPath,
            Quality = job.Quality,
            DataSource = _ds,
            SegmentWorkers = _cfg.seg_workers > 0 ? _cfg.seg_workers : States.SegmentWorkers,
            SegDir = Services.History.PartsDirFor(job.OutPath, _outRoot),
            KeepParts = false,
        };

        DownloadResult res = null;
        try
        {
            res = await Services.Engine.DownloadAsync(req, cb, control, _runCts.Token);
        }
        catch (OperationCanceledException)
        {
            RunUi(() =>
            {
                row.StateWord = States.WordPaused;
                row.Speed = States.EmptyDash;
                row.Eta = States.EmptyDash;
            });
            Log($"‖ {row.Title} 已取消（分片保留，下次可续）");
        }
        catch (Exception ex)
        {
            RunUi(() =>
            {
                row.StateWord = States.WordFailed;
                row.Progress = Math.Max(0, row.Progress);
                row.Speed = States.EmptyDash;
                row.Eta = States.EmptyDash;
            });
            Log($"✗ {row.Title}：" + ex.Message);
            MergeHistory(row, States.WordFailed, 0, 0);
        }
        finally
        {
            lock (_controls) _controls.Remove(control);
            _active--;
            PumpQueue();
            RunUi(() =>
            {
                RebuildView();
                UpdateSummary();
            });
        }

        if (res == null) return;

        if (res.Ok)
        {
            RunUi(() =>
            {
                row.StateWord = res.Size > 0 ? States.WordDone : States.WordExists;
                row.Progress = 100;
                row.Size = LessonRow.FmtSize(res.Size);
                row.Speed = States.EmptyDash;
                row.Eta = States.EmptyDash;
            });
            Log($"✓ {row.Title} 完成 {LessonRow.FmtSize(res.Size)} {Util.FmtDur(res.Duration)}");
            MergeHistory(row, res.Size > 0 ? States.WordDone : States.WordExists, res.Size, res.Duration);
            try
            {
                Services.History.PurgeParts(job.OutPath, _outRoot);
            }
            catch { /* 清缓存失败不影响成品 */ }
        }
        else
        {
            RunUi(() =>
            {
                row.StateWord = States.WordFailed;
                row.Speed = States.EmptyDash;
                row.Eta = States.EmptyDash;
            });
            Log($"✗ {row.Title}：" + res.Message);
            MergeHistory(row, States.WordFailed, res.Size, res.Duration);
        }
    }

    private void BtnPause_Click(object sender, RoutedEventArgs e)
    {
        if (!_running) return;
        _paused = !_paused;
        lock (_controls)
            foreach (var c in _controls) c.Paused = _paused;

        BtnPause.Content = _paused ? "继续" : "暂停";
        foreach (var r in _rows)
        {
            if (_paused && States.IsRunningState(r.StateWord)) r.StateWord = States.WordPaused;
            else if (!_paused && r.StateWord == States.WordPaused && !r.IsHistory) r.StateWord = "下载中";
        }
        Log(_paused ? "‖ 已暂停（分片保留，可继续）" : "▶ 已继续");
        RebuildView();
        UpdateSummary();
    }

    private void BtnCancel_Click(object sender, RoutedEventArgs e)
    {
        if (!_running) return;
        _queue.Clear();
        _runCts?.Cancel();
        Log("已取消本次下载（分片保留，下次可续）");
        BtnPause.IsEnabled = false;
        RebuildView();
        UpdateSummary();
    }

    private void FinishRun()
    {
        _running = false;
        _paused = false;
        BtnRun.IsEnabled = true;
        BtnPause.IsEnabled = false;
        Marq.Text = "";
        int ok = _rows.Count(r => States.IsDoneState(r.StateWord) && !r.IsHistory);
        int fail = _rows.Count(r => States.IsFailedState(r.StateWord) && !r.IsHistory);
        double secs = (Environment.TickCount64 - _runStartTicks) / 1000.0;
        Log($"—— 本批结束：完成 {ok}，失败 {fail}，用时 {Util.FmtClock(secs)}");
        ShowBanner($"下载结束：完成 {ok}，失败 {fail}，用时 {Util.FmtClock(secs)}。", BannerKind.Ok);
        RebuildView();
        UpdateSummary();
    }

    // ══════════════════════════════════════════════════════ 历史

    private void LoadHistory()
    {
        try
        {
            _hist.Clear();
            _hist.AddRange(Services.History.Load());
            _hist.Sort((a, b) => b.ts.CompareTo(a.ts));
            Services.History.PurgeOrphanParts(_hist, _outRoot);
            _checker = Services.CreateChecker(_outRoot);

            _histVm.Clear();
            foreach (var h in _hist.Take(60)) _histVm.Add(new HistVm(h));
            LblHistCount.Text = _hist.Count + " 条";
            LblHist.Text = "上次下载（" + _hist.Count + " 条）";
            Log($"已载入下载历史 {_hist.Count} 条");
        }
        catch (Exception e)
        {
            Log("读取历史失败：" + e.Message);
        }
    }

    private void AppendHistoryRows()
    {
        // 先把旧的历史行摘掉
        for (int i = _rows.Count - 1; i >= 0; i--)
            if (_rows[i].IsHistory) _rows.RemoveAt(i);

        var seen = _rows.Where(r => !r.IsHistory)
                        .Select(r => r.CampName + "|" + r.Title)
                        .ToHashSet();
        foreach (var h in _hist.Take(60))
        {
            string key = (h.camp ?? "") + "|" + (h.title ?? "");
            if (seen.Contains(key)) continue;         // 当前课表里已有 → 用真实行，不重复显示
            if (!string.IsNullOrEmpty(h.path) && File.Exists(h.path) == false) continue;
            _rows.Add(LessonRow.FromHistory(h));
        }
    }

    private void MergeHistory(LessonRow row, string state, long size, double duration)
    {
        try
        {
            string path = row.OutPath;
            if (string.IsNullOrEmpty(path)) return;
            var rec = HistoryRecord.Make(path, row.Title, row.CampName, state,
                size, row.Progress > 0 ? size : 0, size,
                row.Progress, 100, (long)Math.Round(duration));
            Services.History.Merge(_hist, rec);
            _hist.Sort((a, b) => b.ts.CompareTo(a.ts));
            SaveHistory();
            _checker?.Invalidate(row.CampName);
        }
        catch (Exception e)
        {
            Log("写历史失败：" + e.Message);
        }
    }

    private void SaveHistory()
    {
        try
        {
            Services.History.Save(_hist);
            _histVm.Clear();
            foreach (var h in _hist.Take(60)) _histVm.Add(new HistVm(h));
            LblHistCount.Text = _hist.Count + " 条";
        }
        catch (Exception e) { Log("保存历史失败：" + e.Message); }
    }

    private void RemoveHistoryOf(string path)
    {
        _hist.RemoveAll(h => string.Equals(h.path, path, StringComparison.OrdinalIgnoreCase));
        SaveHistory();
    }

    private async void BtnReset_Click(object sender, RoutedEventArgs e)
    {
        bool ok = await MsgBox.ConfirmAsync(this, "重置记录",
            "清空下载历史与「上次下载」列表？\n\n成品文件不会被删除；已存在判定会在下次扫描时重新建立。",
            "重置", "取消");
        if (!ok) return;
        _hist.Clear();
        SaveHistory();
        foreach (var r in _rows.Where(r => !r.IsHistory))
        {
            r.StateWord = "";
            r.Progress = 0;
            r.Size = States.EmptyDash;
            r.OutPath = "";
        }
        for (int i = _rows.Count - 1; i >= 0; i--)
            if (_rows[i].IsHistory) _rows.RemoveAt(i);
        RebuildView();
        UpdateSummary();
        ShowBanner("下载记录已重置。", BannerKind.Ok);
    }

    private void BtnRescan_Click(object sender, RoutedEventArgs e)
    {
        if (_checker == null) _checker = Services.CreateChecker(_outRoot);
        int hit = 0;
        foreach (var r in _rows)
        {
            if (r.IsHistory || r.Lesson == null) continue;
            var st = _checker.Check(r.CampName, Naming.LessonStem(r.Lesson), r.Lesson.Duration);
            if (st != null && st.IsOk)
            {
                r.StateWord = "已存在";
                r.Progress = 100;
                r.Size = LessonRow.FmtSize(st.Size);
                r.OutPath = st.Path;
                hit++;
            }
        }
        RebuildView();
        UpdateSummary();
        ShowBanner($"重新扫描完成：磁盘上已有 {hit} 节成品。", BannerKind.Ok);
        Log($"重新扫描完成：命中 {hit} 节");
    }

    // ══════════════════════════════════════════════════════ 汇总

    private void UpdateSummary()
    {
        int total = _rows.Count(r => !r.IsHistory);
        int pending = _rows.Count(r => !r.IsHistory && States.InDownloadScope(r.StateWord, false));
        int done = _rows.Count(r => !r.IsHistory && States.IsDoneState(r.StateWord));
        int failed = _rows.Count(r => !r.IsHistory && States.IsFailedState(r.StateWord));
        int running = _rows.Count(r => !r.IsHistory && States.IsRunningState(r.StateWord));
        long bytes = _hist.Where(h => h.state == "已完成").Sum(h => h.size);

        LblSummary.Text = total == 0
            ? "暂无课程 · 在左侧勾选营即可并入课表"
            : $"共 {total} 节 · 待下载 {pending} · 进行中 {running} · 已完成 {done}"
              + (failed > 0 ? $" · 失败 {failed}" : "")
              + $" · 历史合计 {LessonRow.FmtSize(bytes)}";

        // 总剩余：按当前平均速率估（只在下载中显示）
        double eta = 0;
        int etaCount = 0;
        foreach (var r in _rows.Where(r => States.IsRunningState(r.StateWord)))
        {
            var t = ParseEta(r.Eta);
            if (t > 0) { eta = Math.Max(eta, t); etaCount++; }
        }
        LblEta.Text = etaCount > 0 ? $"预计还需 {Util.FmtClock(eta)}" : "";
    }

    private static double ParseEta(string s)
    {
        if (string.IsNullOrEmpty(s) || s == States.EmptyDash) return 0;
        var parts = s.Split(':');
        double v = 0;
        foreach (var p in parts)
        {
            if (!int.TryParse(p, out var n)) return 0;
            v = v * 60 + n;
        }
        return v;
    }

    // ══════════════════════════════════════════════════════ 输出目录 / 环境

    private async void BtnBrowse_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
            {
                Title = "选择下载目录",
                AllowMultiple = false,
            });
            if (folders != null && folders.Count > 0)
            {
                EdOut.Text = folders[0].Path.LocalPath;
                ApplyOutDir();
            }
        }
        catch (Exception ex) { Log("选择目录失败：" + ex.Message); }
    }

    private void EdOut_LostFocus(object sender, RoutedEventArgs e) => ApplyOutDir();

    private void EdOut_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Enter) return;
        ApplyOutDir();
        e.Handled = true;
    }

    private void ApplyOutDir()
    {
        string dir = (EdOut.Text ?? "").Trim().Trim('"');
        if (dir.Length == 0) return;
        if (string.Equals(_cfg.out_dir, dir, StringComparison.OrdinalIgnoreCase)) return;
        _cfg.out_dir = dir;
        Config.Save(_cfg);
        _outRoot = dir;
        _checker = Services.CreateChecker(dir);
        Log("下载目录已改为：" + dir);
        ShowBanner("下载目录已更新：" + dir, BannerKind.Ok);
        BtnRescan_Click(null, null);
    }

    private async void BtnEnv_Click(object sender, RoutedEventArgs e)
    {
        var win = new EnvCheckWindow();
        await win.ShowDialog(this);
        // 装完 ffmpeg 可能变了 → 重新探一次，并刷新已存在判定
        if (win.Changed)
        {
            _checker = Services.CreateChecker(_outRoot);
            BtnRescan_Click(null, null);
        }
    }

    // ══════════════════════════════════════════════════════ 窗口交互

    private void BtnWinMin_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;
    private void BtnWinMax_Click(object sender, RoutedEventArgs e) => ToggleMax();
    private void BtnWinClose_Click(object sender, RoutedEventArgs e) => Close();

    private void ToggleMax() =>
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private void OnWinPropertyChanged(object sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property != WindowStateProperty) return;
        if (BtnWinMax != null)
            BtnWinMax.Content = WindowState == WindowState.Maximized ? "❐" : "□";
        UpdateTitleWidth();
    }

    /// <summary>
    /// Avalonia 的 TopLevel 把 PointToScreen 实现为 IRenderRoot 的显式接口方法，
    /// 这里包一层，避免每个调用点都写强转。
    /// </summary>
    private PixelPoint ToScreen(Point p) => ((IRenderRoot)this).PointToScreen(p);

    private void TopBar_PointerPressed(object sender, PointerPressedEventArgs e)
    {
        var src = e.Source as IInputElement;
        if (IsInteractive(src)) return;
        if (e.ClickCount >= 2 && FindAncestor<Border>(src) == BrandBox) { ToggleMax(); return; }
        _pressOnBrand = FindAncestor<Border>(src) == BrandBox;
        BeginDrag(e);
    }

    private void Window_PointerMoved(object sender, PointerEventArgs e) => UpdateDrag(e);

    private void Window_PointerReleased(object sender, PointerReleasedEventArgs e)
    {
        bool moved = _dragMoved;
        bool onBrand = _pressOnBrand;
        EndDrag();
        _pressOnBrand = false;
        if (!moved && onBrand) ShowAbout();
    }

    private void BeginDrag(PointerPressedEventArgs e)
    {
        _dragging = true;
        _dragMoved = false;
        if (WindowState == WindowState.Maximized) WindowState = WindowState.Normal;
        _dragOriginPos = Position;
        _dragStartScreen = ToScreen(e.GetPosition(this));
        _captured = e.Pointer;
        try { e.Pointer.Capture(this); } catch { }
    }

    private void UpdateDrag(PointerEventArgs e)
    {
        if (!_dragging) return;
        var now = ToScreen(e.GetPosition(this));
        int dx = now.X - _dragStartScreen.X;
        int dy = now.Y - _dragStartScreen.Y;
        if (!_dragMoved && Math.Abs(dx) < 3 && Math.Abs(dy) < 3) return;
        _dragMoved = true;
        Position = new PixelPoint(_dragOriginPos.X + dx, _dragOriginPos.Y + dy);
    }

    private void EndDrag()
    {
        if (!_dragging) return;
        _dragging = false;
        try { _captured?.Capture(null); } catch { }
        _captured = null;
    }

    private static bool IsInteractive(IInputElement src)
    {
        var v = src as Visual;
        while (v != null)
        {
            if (v is Button || v is TextBox || v is ComboBox
                || v is CheckBox || v is RadioButton || v is ToggleButton)
                return true;
            v = v.GetVisualParent();
        }
        return false;
    }

    private static T FindAncestor<T>(IInputElement src) where T : class
    {
        var v = src as Visual;
        while (v != null)
        {
            if (v is T t) return t;
            v = v.GetVisualParent();
        }
        return null;
    }

    private void Grip_PointerPressed(object sender, PointerPressedEventArgs e)
    {
        var name = (e.Source as Control)?.Name ?? (sender as Control)?.Name;
        WindowEdge? edge = name switch
        {
            "GripLeft" => WindowEdge.West,
            "GripRight" => WindowEdge.East,
            "GripTop" => WindowEdge.North,
            "GripBottom" => WindowEdge.South,
            "GripTopLeft" => WindowEdge.NorthWest,
            "GripTopRight" => WindowEdge.NorthEast,
            "GripBottomLeft" => WindowEdge.SouthWest,
            "GripBottomRight" => WindowEdge.SouthEast,
            _ => null,
        };
        if (edge == null) return;
        try { BeginResizeDrag(edge.Value, e); } catch { }
        e.Handled = true;
    }

    private void OnKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Q && e.KeyModifiers.HasFlag(KeyModifiers.Control)) { Close(); e.Handled = true; }
        if (e.Key == Key.Escape && Banner.IsVisible) { Banner.IsVisible = false; e.Handled = true; }
    }

    private AboutWindow _about;
    private void ShowAbout()
    {
        try
        {
            if (_about != null) { _about.Activate(); return; }
            _about = new AboutWindow();
            _about.Closed += (_, _) => _about = null;
            _about.Show(this);
        }
        catch (Exception e) { Log("打开「关于」失败：" + e.Message); }
    }

    // ══════════════════════════════════════════════════════ 日志 / 提示

    private enum BannerKind { Info, Ok, Err }

    private void Log(string msg)
    {
        string line = $"[{DateTime.Now:HH:mm:ss}] {msg}";
        void Append()
        {
            string cur = TxtLog.Text ?? "";
            if (cur.Length > 200_000) cur = cur.Substring(cur.Length - 150_000);
            TxtLog.Text = cur + line + Environment.NewLine;
            TxtLog.CaretIndex = TxtLog.Text.Length;
        }
        if (Dispatcher.UIThread.CheckAccess()) Append();
        else Dispatcher.UIThread.Post(Append);
    }

    private void RunUi(Action action)
    {
        if (Dispatcher.UIThread.CheckAccess()) action();
        else Dispatcher.UIThread.Post(action);
    }

    private void ShowBanner(string msg, BannerKind kind)
    {
        void Apply()
        {
            Banner.IsVisible = true;
            string bg, bd, fg;
            switch (kind)
            {
                case BannerKind.Ok: bg = "#EAF3DE"; bd = "#B7D79A"; fg = "#3B6D11"; break;
                case BannerKind.Err: bg = "#FCEBEB"; bd = "#EFB3B3"; fg = "#A32D2D"; break;
                default: bg = "#E8F1FB"; bd = "#B9D4EF"; fg = "#185FA5"; break;
            }
            Banner.Background = new SolidColorBrush(Color.Parse(bg));
            Banner.BorderBrush = new SolidColorBrush(Color.Parse(bd));
            LblBanner.Foreground = new SolidColorBrush(Color.Parse(fg));
            LblBanner.Text = msg;
        }
        RunUi(Apply);

        if (_bannerTimer == null)
        {
            _bannerTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(7) };
            _bannerTimer.Tick += (_, _) => { _bannerTimer.Stop(); Banner.IsVisible = false; };
        }
        _bannerTimer.Stop();
        _bannerTimer.Start();
    }

    private void BtnClearLog_Click(object sender, RoutedEventArgs e) => TxtLog.Text = "";

    /// <summary>窗口关闭：取消后台下载与授权轮询，避免残留线程。</summary>
    protected override void OnClosed(EventArgs e)
    {
        try { _runCts?.Cancel(); } catch { }
        try { _uiCts?.Cancel(); } catch { }
        try { Services.Auth.CloseAll(); } catch { }
        base.OnClosed(e);
    }
}
