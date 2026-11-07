using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using Xqd.Core;
using Xqd.Gui.Controls;
using Xqd.Gui.ViewModels;

namespace Xqd.Gui;

/// <summary>
/// 桌面主界面 —— 完整移植 xqd_gui.MainWindow（v1.5.1）。
/// 所有跨线程回调一律经 Ui() 用 Dispatcher.InvokeAsync 回到 UI 线程。
/// 状态词 / 列号一律取自 States，绝不硬编码。
/// </summary>
public partial class MainWindow : Window
{
    // ── 配置 / 服务 ──────────────────────────────────────────
    private readonly Dispatcher _ui;
    private AppConfig _cfg;
    private string _outDir;
    private string _quality = "max";
    private string _platformId = "qianliao";
    private string _cookie = "";
    private IPlatform _platform;
    private IDataSource _dataSource;
    private IExistingChecker _checker;
    private string _checkerRoot = "";

    private List<HistoryRecord> _history = new();
    private double _histLastFlush;

    // ── 表格数据 ────────────────────────────────────────────
    private readonly ObservableCollection<CampItem> _campItems = new();
    private readonly ObservableCollection<LessonRow> _lessonRows = new();
    private readonly ObservableCollection<TaskRow> _taskRows = new();

    private Camp _currentCamp;
    private string _selectedTab = States.Tabs[0];
    private List<Camp> _campTarget = new();
    private List<(Camp Camp, List<LessonRow> Rows)> _lessonGroups = new();

    // ── 下载调度 ────────────────────────────────────────────
    private readonly Dictionary<int, Job> _jobs = new();
    private readonly List<Job> _pendingQueue = new();
    private readonly HashSet<int> _runningWorkers = new();
    private readonly HashSet<int> _networkReleased = new();
    private int _jobSeq;

    private HashSet<string> _checkedLessonKeys = new(StringComparer.Ordinal);
    private int _catalogGen;
    private int _scanGen;
    private bool _rebuildScheduled;
    private bool _campUpdating;
    private bool _lessonBulk;
    private bool _paused;
    private bool _authBusy;
    private string _campHeaderState = "none";
    private string _lessonHeaderState = "none";
    private int _scanExist;
    private int _scanBroken;

    private readonly DownloadControl _control = new();
    private readonly CancellationTokenSource _appCts = new();
    private readonly DispatcherTimer _etaTimer;
    private const double MuxDiskSpeed = 10.0 * 1024 * 1024;

    public MainWindow()
    {
        InitializeComponent();
        _ui = Dispatcher;

        Title = States.AppTitle + "  v" + States.AppVersion;
        LblVersion.Text = "兴趣岛 · " + States.AppVersion;

        _cfg = Config.Load();
        _outDir = Config.EffectiveOutDir(_cfg);
        _quality = string.IsNullOrEmpty(_cfg.quality) ? "max" : _cfg.quality;
        _platformId = string.IsNullOrEmpty(_cfg.platform) ? "qianliao" : _cfg.platform;
        ChkAutoLaunch.IsChecked = _cfg.auto_launch;
        ChkAutoClose.IsChecked = _cfg.auto_close;

        EdOut.Text = _outDir;
        CmbQuality.SelectedIndex = _quality == "720" ? 1 : 0;

        _checkerRoot = _outDir;
        _checker = Services.CreateChecker(_outDir);
        _history = Services.History.Load() ?? new List<HistoryRecord>();

        TabList.ItemsSource = States.Tabs;
        TabList.SelectedIndex = 0;
        LstCamps.ItemsSource = _campItems;
        LstLessons.ItemsSource = _lessonRows;
        LstTasks.ItemsSource = _taskRows;

        // 表头「全选」三态复选框（放在 GridViewColumn.Header 里，用代码订阅避免模板事件歧义）
        var lh = LessonsGrid.Columns[States.ColCheck].Header as CheckBox;
        if (lh != null) lh.Click += ChkLessonAll_Click;

        System.Diagnostics.Debug.Assert(LessonsGrid.Columns.Count == States.LessonColumnCount);
        System.Diagnostics.Debug.Assert(TasksGrid.Columns.Count == States.TaskColumnCount);

        RestoreHistoryTasks();
        try { Services.History.PurgeOrphanParts(_history); }
        catch (Exception e) { Log("清理分片缓存失败：" + e.Message); }

        _etaTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _etaTimer.Tick += (_, _) => TickEta();
        _etaTimer.Start();

        AdjustColumnWidths();

        // ★ 启动优先用本机保存授权（forceMumu:false）—— 平时绝不启动 MuMu。
        _ = AutoCheckAuthAsync(false);
    }

    private GridView LessonsGrid => (GridView)LstLessons.View;
    private GridView TasksGrid => (GridView)LstTasks.View;

    private static double Now() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;

    /// <summary>所有跨线程 UI 更新入口：后台线程 → Dispatcher.InvokeAsync；UI 线程直接执行。</summary>
    private void Ui(Action a)
    {
        if (_ui.CheckAccess()) a();
        else _ui.InvokeAsync(a);
    }

    private string Root
    {
        get
        {
            var t = EdOut.Text.Trim();
            return t.Length > 0 ? t : _outDir;
        }
    }

    // ══════════════════════ 授权 ══════════════════════════════
    private async Task AutoCheckAuthAsync(bool forceMumu)
    {
        if (_authBusy) return;
        _authBusy = true;
        BtnRetry.IsEnabled = false;
        LblAuth.Text = "授权：检查中…";
        Banner.Visibility = Visibility.Collapsed;
        bool autoLaunch = ChkAutoLaunch.IsChecked == true;
        bool autoClose = ChkAutoClose.IsChecked == true;
        try
        {
            var r = await Services.Auth.EnsureAuthAsync(
                forceMumu, s => Ui(() => OnAuthStatus(s)), autoLaunch, autoClose, _appCts.Token);
            _cookie = r.Ok ? r.Cookie : "";
            if (r.Ok)
            {
                LoadPlatform();
                LblAuth.Text = r.FromCache ? "授权：已就绪（本机保存）" : "授权：已就绪";
                SetBanner("ok", r.FromCache
                    ? "已使用本机保存的授权，未启动 MuMu 模拟器。若授权过期，点右上「重新授权」刷新。"
                    : "授权成功。工具已可独立运行，模拟器和 App 可以关闭。");
                Log(r.FromCache
                    ? "使用本机保存的授权（未启动模拟器）。"
                    : "授权成功。已保存到本机私有文件，下次启动无需模拟器。");
                await LoadCampsAsync();
            }
            else
            {
                LblAuth.Text = "授权：未就绪";
                SetBanner("err", r.Message);
                Log("授权未就绪：" + FirstLine(r.Message));
            }
        }
        catch (Exception ex)
        {
            LblAuth.Text = "授权：未就绪";
            SetBanner("err", ex.Message);
            Log("授权检查异常：" + ex.Message);
        }
        finally
        {
            _authBusy = false;
            BtnRetry.IsEnabled = true;
        }
    }

    private void OnAuthStatus(string s)
    {
        LblAuth.Text = "授权：" + s;
        Log(s);
    }

    private void LoadPlatform()
    {
        try
        {
            _platform = Services.CreatePlatform(_platformId, _cookie);
            _dataSource = _platform;       // 已授权实例，填进 DownloadRequest.DataSource
        }
        catch (Exception e)
        {
            Log("加载平台失败：" + e.Message);
            _platform = null;
            _dataSource = null;
        }
    }

    private void SetBanner(string kind, string text)
    {
        TxtBanner.Text = text ?? "";
        Banner.Visibility = Visibility.Visible;
        if (kind == "ok")
        {
            Banner.Background = C("#EAF7EE");
            Banner.BorderBrush = C("#B8E0C4");
            TxtBanner.Foreground = C("#1F7A3D");
        }
        else if (kind == "err")
        {
            Banner.Background = C("#FDEEEE");
            Banner.BorderBrush = C("#F0C2C2");
            TxtBanner.Foreground = C("#B03030");
        }
        else
        {
            Banner.Background = C("#FFF8E6");
            Banner.BorderBrush = C("#F0DFAE");
            TxtBanner.Foreground = C("#8A6D1A");
        }
    }

    private static SolidColorBrush C(string hex)
    {
        var b = new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex));
        b.Freeze();
        return b;
    }

    // ══════════════════════ 营（标签 / 勾选 / 全选三态） ══════════════════════
    private async Task LoadCampsAsync()
    {
        if (_platform == null || string.IsNullOrEmpty(_cookie)) return;
        var prev = new HashSet<string>(
            _campItems.Where(c => c.IsChecked).Select(c => c.Key), StringComparer.Ordinal);
        LblCampHint.Text = "加载中…";
        Log("加载" + _selectedTab + "列表…");
        try
        {
            var camps = await _platform.ListCampsAsync(_selectedTab, _appCts.Token).ConfigureAwait(true);
            Ui(() => ApplyCamps(camps ?? new List<Camp>(), prev));
        }
        catch (Exception e)
        {
            Ui(() =>
            {
                LblCampHint.Text = "加载失败";
                Log("加载营列表失败：" + e.Message);
                SetBanner("err", "加载营列表失败，可能是本机保存的授权已过期或网络不稳定。请点右上「重新授权」从模拟器刷新。");
            });
        }
    }

    private void ApplyCamps(List<Camp> camps, HashSet<string> prev)
    {
        _campUpdating = true;
        _campItems.Clear();
        foreach (var c in camps)
        {
            var item = new CampItem(c);
            item.SetCheckedSilently(prev.Contains(item.Key));
            item.CheckChanged = OnCampItemCheckChanged;
            _campItems.Add(item);
        }
        _campUpdating = false;
        SyncAllCampsCheckbox();
        Log(_selectedTab + "：" + camps.Count + " 个");
        if (camps.Count > 0)
        {
            _currentCamp = camps[0];
            LstCamps.SelectedIndex = 0;
            ScheduleRebuild();
        }
    }

    private void OnCampItemCheckChanged(CampItem item)
    {
        if (_campUpdating) return;
        SyncAllCampsCheckbox();
        ScheduleRebuild();
    }

    private List<Camp> CheckedCamps() =>
        _campItems.Where(c => c.IsChecked).Select(c => c.Camp).ToList();

    private void SyncAllCampsCheckbox()
    {
        int n = _campItems.Count;
        int k = _campItems.Count(c => c.IsChecked);
        _campHeaderState = k == 0 ? "none" : (k == n && n > 0 ? "all" : "partial");
        ChkAllCamps.IsChecked = _campHeaderState == "all" ? true
            : _campHeaderState == "none" ? (bool?)false : null;
        LblCampHint.Text = n + " 个营" + (k > 0 ? " · 已勾选 " + k + " 个" : "");
    }

    private static string CampKey(Camp c) => string.IsNullOrEmpty(c.CampId) ? c.Name : c.CampId;

    private void ScheduleRebuild()
    {
        if (_rebuildScheduled) return;
        _rebuildScheduled = true;
        _ui.BeginInvoke(new Action(RebuildLessonsFromCamps));
    }

    private void RebuildLessonsFromCamps()
    {
        _rebuildScheduled = false;
        var picked = CheckedCamps();
        if (picked.Count == 0 && _currentCamp != null) picked = new List<Camp> { _currentCamp };
        var keys = picked.Select(CampKey).ToList();
        var old = _campTarget.Select(CampKey).ToList();
        if (keys.SequenceEqual(old) && _lessonRows.Count > 0) return;
        _campTarget = picked.ToList();
        LoadCampsLessons(picked);
    }

    // ══════════════════════ 课表（多营合并 / 跑马灯） ══════════════════════
    private void LoadCampsLessons(List<Camp> camps)
    {
        SnapshotLessonChecks();
        _catalogGen++;
        int gen = _catalogGen;
        _scanGen++;                       // 作废旧扫描结果
        _lessonGroups.Clear();
        _lessonRows.Clear();
        LblExist.Text = "";
        UpdateLessonTitle(camps, 0);
        UpdateLessonHeader(0);
        if (camps.Count == 0 || _platform == null)
        {
            LblLessonsHint.Text = "选择左侧营查看课程";
            return;
        }
        LblLessonsHint.Text = "正在加载 " + camps.Count + " 个营的课表…";
        _ = CatalogWorkerAsync(camps, gen);
    }

    private async Task CatalogWorkerAsync(List<Camp> camps, int gen)
    {
        try
        {
            foreach (var camp in camps)
            {
                List<Lesson> lessons;
                try { lessons = await _platform.CampCatalogAsync(camp, _appCts.Token).ConfigureAwait(false); }
                catch (Exception e)
                {
                    Ui(() => { if (gen == _catalogGen) Log("加载课表失败：" + camp.Name + " —— " + e.Message); });
                    continue;
                }
                var snapshot = lessons ?? new List<Lesson>();
                Ui(() =>
                {
                    if (gen != _catalogGen) return;
                    var rows = AppendLessonRows(camp, snapshot);
                    _lessonGroups.Add((camp, rows));
                    UpdateLessonTitle(_lessonGroups.Select(g => g.Camp).ToList(), _lessonRows.Count);
                    UpdateLessonHeader(0);
                    if (_lessonGroups.Count == 1)
                        LblLessonsHint.Text = "共 " + _lessonRows.Count + " 节 · 目录：" +
                            Path.Combine(Root, Naming.CampFolder(camp.Name));
                    else
                        LblLessonsHint.Text = "共 " + _lessonRows.Count + " 节 · " + _lessonGroups.Count +
                            " 个营 · 各自存到下载目录下的同名文件夹";
                });
            }
            Ui(() =>
            {
                if (gen != _catalogGen) return;
                if (_lessonGroups.Count == 0)
                {
                    LblLessonsHint.Text = "课表加载失败，请检查网络后点「刷新」";
                    return;
                }
                ScanExisting();
            });
        }
        catch (Exception e) { Ui(() => Log("课表加载异常：" + e.Message)); }
    }

    private void SnapshotLessonChecks()
    {
        _checkedLessonKeys = new HashSet<string>(
            _lessonRows.Where(r => r.IsChecked).Select(r => r.Key), StringComparer.Ordinal);
    }

    private List<LessonRow> AppendLessonRows(Camp camp, List<Lesson> lessons)
    {
        var rows = new List<LessonRow>();
        _lessonBulk = true;
        foreach (var le in lessons)
        {
            le.CampOfRow = camp;         // ★ 每行绑定所属营（输出/检测/历史都按它算）
            var row = new LessonRow(le, camp, le.Seq);
            row.CheckChanged = OnLessonRowCheckChanged;
            row.SetCheckedSilently(_checkedLessonKeys.Contains(row.Key));
            row.OutPath = OutPathFor(camp, le);
            var p = InitialProgress(le, camp);
            row.Progress = p.pct;
            row.ProgressTip = p.tip;
            _lessonRows.Add(row);
            rows.Add(row);
        }
        _lessonBulk = false;
        UpdateLessonHeaderState();
        return rows;
    }

    private void OnLessonRowCheckChanged(LessonRow row)
    {
        if (_lessonBulk) return;
        UpdateLessonHeaderState();
    }

    private void UpdateLessonTitle(List<Camp> camps, int total)
    {
        var names = camps.Select(c => c.Name).ToList();
        if (names.Count == 0) { Marquee.SetText("（0 节）", false); return; }
        if (names.Count == 1)
        {
            Marquee.SetText(names[0] + "（" + total + " 节）", false, "当前显示：" + names[0]);
            return;
        }
        string text = string.Join(States.CampSeparator, names) + States.CampSeparator + "共 " + total + " 节";
        string tip = "已勾选 " + names.Count + " 个营（标题会向左循环滚动）：\n" + string.Join("\n", names);
        Marquee.SetText(text, true, tip);
    }

    private void UpdateLessonHeader(int exist)
    {
        int total = _lessonRows.Count;
        if (total == 0) return;
        LessonsGrid.Columns[States.ColTitle].Header = "课程 (" + exist + "/" + total + ")";
    }

    private void UpdateLessonHeaderState()
    {
        int total = _lessonRows.Count;
        int k = _lessonRows.Count(r => r.IsChecked);
        _lessonHeaderState = k == 0 ? "none" : (k == total && total > 0 ? "all" : "partial");
        var cb = LessonsGrid.Columns[States.ColCheck].Header as CheckBox;
        if (cb != null)
            cb.IsChecked = _lessonHeaderState == "all" ? true
                : _lessonHeaderState == "none" ? (bool?)false : null;
    }

    private void SetAllLessonChecks(bool v)
    {
        _lessonBulk = true;
        foreach (var r in _lessonRows) r.SetCheckedSilently(v);
        _lessonBulk = false;
    }

    // ══════════════════════ 进度恢复（四来源） ══════════════════════
    private (int pct, string tip) InitialProgress(Lesson le, Camp camp)
    {
        // ① 活动任务实时进度
        foreach (var job in _jobs.Values)
        {
            if (!ReferenceEquals(job.Lesson, le)) continue;
            int p = job.Percent();
            if (p > 0) return (p, "下载进度：" + p + "%");
        }
        string outPath;
        try { outPath = OutPathFor(camp, le); }
        catch { return (0, ""); }

        // ② 下载历史（done_dur/total_dur 或 down/total）
        var rec = FindHistory(outPath);
        if (rec != null)
        {
            if (rec.state == States.WordDone) return (100, "已完成（100%）");
            int pct = 0;
            if (rec.total_dur > 0 && rec.done_dur > 0)
                pct = (int)(rec.done_dur * 100 / rec.total_dur);
            if (rec.total > 0 && rec.down > 0 && pct == 0)
                pct = (int)(rec.down * 100.0 / rec.total);
            // ③ 可续传分片缓存字节数
            var pp = Services.History.PartsProgress(Services.History.PartsDirFor(outPath));
            if (pp.Bytes > 0 && rec.total > 0)
                pct = Math.Max(pct, (int)(pp.Bytes * 100.0 / rec.total));
            pct = Math.Max(pct, (int)le.Progress);
            pct = Math.Max(0, Math.Min(99, pct));   // 未完成一律封顶 99%
            if (pct > 0)
                return (pct, "未完成（可续传）：" + pct + "%" +
                    (pp.Count > 0 ? "，缓存分片 " + pp.Count + " 个" : ""));
        }
        // ④ 磁盘已有成品但历史没记上（手工拷入）
        try
        {
            if (File.Exists(outPath) && new FileInfo(outPath).Length > 10240)
                return (100, "已存在成品（100%）");
        }
        catch { }
        return (0, "");
    }

    private HistoryRecord FindHistory(string path)
    {
        foreach (var r in _history)
            if (string.Equals(r.path, path, StringComparison.OrdinalIgnoreCase)) return r;
        try
        {
            var norm = Path.GetFullPath(path).ToLowerInvariant();
            foreach (var r in _history)
                if (Path.GetFullPath(r.path ?? "").ToLowerInvariant() == norm) return r;
        }
        catch { }
        return null;
    }

    private void SetRowProgress(LessonRow row, int pct, string tip = "")
    {
        row.Progress = Math.Max(0, Math.Min(100, pct));
        if (!string.IsNullOrEmpty(tip)) row.ProgressTip = tip;
    }

    // ══════════════════════ 已下载检测 ══════════════════════
    private void RescanExisting()
    {
        if (_lessonGroups.Count == 0)
        {
            MessageBox.Show(this, "请先选择一个营。", "提示");
            return;
        }
        SyncChecker();
        _checker.Invalidate("");
        ScanExisting();
    }

    private void ScanExisting()
    {
        var groups = _lessonGroups.Count > 0
            ? _lessonGroups.Select(g => (g.Camp, g.Rows)).ToList()
            : new List<(Camp, List<LessonRow>)>();
        if (groups.Count == 0) return;
        SyncChecker();
        int gen = ++_scanGen;
        var checker = _checker;
        string root = Root;
        Task.Run(() => ScanWorker(groups, gen, checker, root));
    }

    private void ScanWorker(List<(Camp, List<LessonRow>)> groups, int gen,
                            IExistingChecker checker, string root)
    {
        try
        {
            var all = new List<(LessonRow Row, bool Ok, ExistingState St)>();
            int n = 0;
            foreach (var g in groups)
            {
                var folder = Path.Combine(root, Naming.CampFolder(g.Item1.Name));
                foreach (var row in g.Item2)
                {
                    var st = checker.Check(folder, Naming.LessonStem(row.Lesson), row.Lesson.Duration);
                    if (st.Status != "missing") all.Add((row, st.IsOk, st));
                    n++;
                    if (n % 10 == 9 && all.Count > 0)
                    {
                        var send = all.ToList();
                        Ui(() => { if (gen == _scanGen) OnScanDone(send); });
                    }
                }
            }
            var rest = all.ToList();
            Ui(() =>
            {
                if (gen != _scanGen) return;
                OnScanDone(rest);
                OnScanFinished();
            });
        }
        catch (Exception e) { Ui(() => Log("已下载检测异常：" + e.Message)); }
    }

    private void OnScanDone(List<(LessonRow Row, bool Ok, ExistingState St)> result)
    {
        int exist = 0, broken = 0;
        foreach (var (row, ok, st) in result)
        {
            if (row == null || !_lessonRows.Contains(row)) continue;   // 按对象引用，切营后旧结果作废
            if (ok) exist++; else broken++;
            MarkExisting(row, ok, st);
        }
        _scanExist = exist;
        _scanBroken = broken;
        LblExist.Text = "正在检测已下载课程…";
        UpdateLessonHeader(exist);
        UpdateLessonHeaderState();
    }

    private void OnScanFinished()
    {
        UpdateLessonHeader(_scanExist);
        LblExist.Text = (_scanExist > 0 || _scanBroken > 0)
            ? "本目录已有 " + _scanExist + " 节成品，已自动取消勾选并跳过" +
              (_scanBroken > 0 ? "；另有 " + _scanBroken + " 节文件不完整，将重新下载" : "")
            : "";
        Log("已下载检测：" + _scanExist + " 节已存在，" + _scanBroken + " 节需重下");
        UpdateLessonHeaderState();
    }

    private void MarkExisting(LessonRow row, bool ok, ExistingState st)
    {
        var le = row.Lesson;
        // 迟到的扫描结果不能盖掉「排队中 / 正在下载」；但已完成/失败允许被覆盖
        if (le.State == "queued" || le.State == "running") return;
        le.State = ok ? "exists" : "needs_redl";
        le.OutPath = st.Path ?? "";
        if (ok)
        {
            row.StateWord = States.WordExists;
            row.ToolTip = le.Title + "\n已存在：" + st.Path +
                "\n大小：" + (st.Size / 1048576.0).ToString("0.0") + " MB" +
                (st.Duration > 0 ? "\n时长：" + Util.FmtDur(st.Duration) : "");
            SetRowProgress(row, 100, "已存在成品（100%）");
        }
        else
        {
            row.StateWord = States.WordRetry;
            row.ToolTip = le.Title + "\n文件不完整，需要重下";
            int cur = row.Progress;
            if (cur >= 100) cur = 0;      // 之前乐观按「文件存在」置满，扫描证明残缺
            SetRowProgress(row, cur, "文件不完整，需要重下");
        }
        // 已存在 → 取消勾选；残缺 → 勾上（需要重下）
        row.SetCheckedSilently(!ok);
    }

    // ══════════════════════ 下载 ══════════════════════
    private string OutPathFor(Camp camp, Lesson le)
    {
        string name = Naming.CourseFilename(le);
        string folder = Path.Combine(Root, Naming.CampFolder(camp.Name));
        return Path.Combine(folder, name);
    }

    private List<LessonRow> CheckedLessons() => _lessonRows.Where(r => r.IsChecked).ToList();

    private void StartDownloadSelected()
    {
        var picked = CheckedLessons();
        if (picked.Count == 0)
        {
            MessageBox.Show(this, "请先勾选要下载的课程。", "提示");
            return;
        }
        StartDownloads(picked);
    }

    private void StartDownloads(List<LessonRow> picked)
    {
        if (_platform == null || string.IsNullOrEmpty(_cookie))
        {
            MessageBox.Show(this, "请先完成授权。", "未授权", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }
        SyncChecker();
        string root = Root;
        if (!Directory.Exists(root))
        {
            try { Directory.CreateDirectory(root); }
            catch (Exception e)
            {
                MessageBox.Show(this, "无法创建目录：\n" + root + "\n" + e.Message,
                    "目录错误", MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }
        }
        string quality = _quality;      // 画质入队时锁定
        int started = 0, skipped = 0, redownload = 0;

        foreach (var row in picked)
        {
            var le = row.Lesson;
            var camp = row.CampOfRow ?? le.CampOfRow ?? _currentCamp;
            if (camp == null) continue;
            var folder = Path.Combine(root, Naming.CampFolder(camp.Name));
            var stem = Naming.LessonStem(le);
            var st = _checker.Check(folder, stem, le.Duration);

            if (st.IsOk)               // 已下载自动跳过（只记日志，不弹窗）
            {
                skipped++;
                le.State = "exists";
                le.OutPath = st.Path;
                MarkExisting(row, true, st);
                Log("跳过（已存在且完整）：" + le.Title);
                continue;
            }

            string outPath = OutPathFor(camp, le);
            if (st.Status == "broken")   // 残件清理后用规范名覆盖重下
            {
                int removed = PurgeBroken(folder, stem);
                redownload++;
                Log("重下（文件不完整）：" + le.Title + " —— 已清理残缺文件 " + removed + " 个");
            }

            le.State = "queued";
            le.OutPath = outPath;
            if (QueuedLessons().Any(x => ReferenceEquals(x, le)))
            {
                Log("已在下载队列中，跳过重复入队：" + le.Title);
                continue;
            }

            _jobSeq++;
            var job = new Job
            {
                JobId = _jobSeq,
                Lesson = le,
                Camp = camp,
                OutPath = outPath,
                Quality = quality,
                SegDir = Services.History.PartsDirFor(outPath),
            };
            var pp = Services.History.PartsProgress(job.SegDir);
            job.CachedBytes = pp.Bytes;
            job.CachedSegs = pp.Count;
            _jobs[job.JobId] = job;
            _pendingQueue.Add(job);
            SetRowState(row, States.WordQueued, null);
            row.IsChecked = true;       // 入队即自动勾上
            started++;
        }

        string msg = "已启动 " + started + " 个下载任务";
        if (skipped > 0) msg += "，跳过 " + skipped + " 个（已存在且完整）";
        if (redownload > 0) msg += "，重下 " + redownload + " 个（原文件残缺）";
        Log(msg + "。");
        UpdateLessonHeaderState();   // 跳过/入队改过勾选，同步表头三态
        PumpQueue();
    }

    private static int PurgeBroken(string folder, string stem)
    {
        int n = 0;
        try
        {
            if (!Directory.Exists(folder)) return 0;
            foreach (var f in Directory.EnumerateFiles(folder).ToList())
            {
                var name = Path.GetFileNameWithoutExtension(f);
                var ext = Path.GetExtension(f).ToLowerInvariant();
                if (ext != ".mp4" && ext != ".mp3" && ext != ".m4a" && ext != ".aac" &&
                    ext != ".mov" && ext != ".mkv" && ext != ".webm") continue;
                if (name == stem || name.StartsWith(stem + "-", StringComparison.Ordinal))
                {
                    try { File.Delete(f); n++; }
                    catch { /* 单个删不掉跳过 */ }
                }
            }
        }
        catch { }
        return n;
    }

    private List<Lesson> QueuedLessons()
    {
        var s = new List<Lesson>();
        foreach (var j in _pendingQueue) s.Add(j.Lesson);
        foreach (var id in _runningWorkers)
        {
            var j = GetJob(id);
            if (j != null) s.Add(j.Lesson);
        }
        return s;
    }

    // ══════════════════════ 调度（网络槽 / 本地封装槽） ══════════════════════
    private int NetActive() => _runningWorkers.Count(id => !_networkReleased.Contains(id));

    private HashSet<int> ReleaseIdleSlots()
    {
        _networkReleased.IntersectWith(_runningWorkers);   // 清掉已结束任务的残留
        var freed = new HashSet<int>();
        foreach (var id in _runningWorkers.ToList())
        {
            if (_networkReleased.Count >= States.MaxMuxWorkers) break;
            if (_networkReleased.Contains(id)) continue;
            var job = GetJob(id);
            if (job == null || !States.LocalPhases.Contains(job.Phase)) continue;
            _networkReleased.Add(id);
            freed.Add(id);
        }
        return freed;
    }

    private void PumpQueue()
    {
        while (_pendingQueue.Count > 0
               && NetActive() < States.MaxLessonWorkers
               && _runningWorkers.Count < States.MaxLessonWorkers + States.MaxMuxWorkers)
        {
            if (_paused) break;         // 暂停期间不放行新任务
            var job = _pendingQueue[0];
            _pendingQueue.RemoveAt(0);
            if (_runningWorkers.Contains(job.JobId)) continue;
            _runningWorkers.Add(job.JobId);
            job.Lesson.State = "running";
            job.T0 = Now();
            job.Phase = "解析";
            var row = RowOfLesson(job.Lesson);
            if (row != null) SetRowState(row, States.PhaseWord("下载"), null);
            EnsureTaskRow(job, States.PhaseWord("下载"));
            _ = RunJobAsync(job, BuildRequest(job), MakeCallbacks(job));
        }
        SyncPauseButton();
    }

    private Job GetJob(int id) => _jobs.TryGetValue(id, out var j) ? j : null;

    private DownloadRequest BuildRequest(Job job) => new DownloadRequest
    {
        Camp = job.Camp,
        Lesson = job.Lesson,
        OutPath = job.OutPath,
        Quality = job.Quality,
        SegmentWorkers = States.SegmentWorkers,
        PlayUrl = "",                    // 引擎现场解析
        DataSource = _dataSource,        // 已授权的 IDataSource 实例
        SegDir = job.SegDir,
        KeepParts = false,
    };

    private DownloadCallbacks MakeCallbacks(Job job) => new DownloadCallbacks
    {
        Phase = p => Ui(() => OnPhase(job, p)),
        Progress = pi => Ui(() => OnProgress(job, pi)),
        Log = m => Ui(() => Log(m)),
    };

    private async Task RunJobAsync(Job job, DownloadRequest req, DownloadCallbacks cb)
    {
        try
        {
            var r = await Services.Engine.DownloadAsync(req, cb, _control, job.Cts.Token)
                                  .ConfigureAwait(false);
            Ui(() => OnDownloadCompleted(job, r));
        }
        catch (OperationCanceledException)
        {
            Ui(() => OnDownloadCompleted(job,
                new DownloadResult { Ok = false, Message = "已取消", OutPath = job.OutPath }));
        }
        catch (Exception ex)
        {
            Ui(() => OnDownloadCompleted(job,
                new DownloadResult { Ok = false, Message = ex.Message, OutPath = job.OutPath }));
        }
    }

    // ══════════════════════ 回调（均在 UI 线程） ══════════════════════
    private void OnProgress(Job job, ProgressInfo pi)
    {
        job.Down = pi.DoneBytes;
        job.Total = pi.TotalBytes;
        job.DoneDur = pi.DoneDuration;
        job.TotalDur = pi.TotalDuration;

        job.Bmeter.Add(pi.DoneBytes);
        job.Speed = job.Bmeter.Speed();

        int pct;
        if (pi.TotalDuration > 0)                  // 分片视频：内容时长口径
        {
            job.Meter.Add(pi.DoneDuration);
            job.RateDur = job.Meter.Speed();
            job.Unit = "dur";
            pct = (int)Math.Max(0, Math.Min(100, pi.DoneDuration * 100 / pi.TotalDuration));
        }
        else                                       // 直链音频：字节口径
        {
            job.RateDur = job.Speed;
            job.Unit = "byte";
            pct = pi.TotalBytes > 0
                ? (int)Math.Max(0, Math.Min(100, pi.DoneBytes * 100.0 / pi.TotalBytes)) : 0;
        }
        job.Eta = ComputeEta(job);
        RefreshTaskRow(job);

        // 进度写历史（节流 3 秒）
        double now = Now();
        if (now - _histLastFlush > 3.0)
        {
            _histLastFlush = now;
            RecordHistory(job.OutPath, job.Lesson?.Title ?? "", job.Camp?.Name ?? "",
                States.PhaseWord("下载"), pi.DoneBytes, pi.TotalBytes, pi.DoneDuration, pi.TotalDuration,
                (long)(job.Lesson?.Duration ?? 0));
            FlushHistory();
        }

        if (job.Lesson != null) job.Lesson.Progress = pct;
        var row = RowOfLesson(job.Lesson);
        if (row != null) SetRowProgress(row, pct, "下载进度：" + pct + "%");
    }

    private void OnPhase(Job job, string phase)
    {
        string old = job.Phase ?? "";
        job.Phase = phase;
        if (phase == "封装") job.EtaFixed = EstimateMuxSeconds(job);
        else if (phase == "校验") job.EtaFixed = 3.0;

        // 一进封装/校验立即归还网络槽位，放行下一节
        var freed = States.LocalPhases.Contains(phase) ? ReleaseIdleSlots() : new HashSet<int>();
        if (freed.Count > 0) PumpQueue();
        RefreshTaskRow(job);

        string word = States.PhaseWord(phase);
        if (_paused) return;            // 暂停中不改状态（用户操作优先级更高）
        SetBothStates(job, word);
        if (word != States.PhaseWord(old))
        {
            string note = freed.Contains(job.JobId) ? "（网络已释放，可并行下一节）" : "";
            LogState(word + "：" + (job.Lesson?.Title ?? "") + note);
        }
    }

    private void OnDownloadCompleted(Job job, DownloadResult r)
    {
        // 先释放槽位、放行下一节（封装完成可能空出本地槽 → 连续放行两节）
        _runningWorkers.Remove(job.JobId);
        _networkReleased.Remove(job.JobId);
        ReleaseIdleSlots();
        PumpQueue();
        SyncPauseButton();

        var le = job.Lesson;
        if (le == null) return;
        var row = RowOfLesson(le);
        bool ok = r != null && r.Ok;
        job.Finished = true;
        if (ok)
        {
            le.State = "done";
            le.Progress = 100;
            le.OutPath = string.IsNullOrEmpty(r.OutPath) ? le.OutPath : r.OutPath;
            SetBothStates(job, States.WordDone, r.Message, force: true);
            if (row != null) SetRowProgress(row, 100, "已完成（100%）");
            UpdateTaskFinished(job, States.WordDone, r.Message);
            try { _checker.Invalidate(Path.GetDirectoryName(le.OutPath)); } catch { }
            Log("已完成：" + le.Title + "（" + r.Message + "）");
        }
        else
        {
            le.State = "failed";
            SetBothStates(job, States.WordFailed, r?.Message, force: true);
            if (row != null) row.IsChecked = true;   // 失败自动重新勾选
            UpdateTaskFinished(job, States.WordFailed, r?.Message);
            Log("失败：" + le.Title + " —— " + (r?.Message ?? "") +
                "（已重新勾选，可再点「下载选中」重试）");
        }
    }

    // ══════════════════════ 速率 / ETA ══════════════════════
    private static double? ComputeEta(Job job)
    {
        double total, done, speed;
        if (job.Unit == "dur") { total = job.TotalDur; done = job.DoneDur; speed = job.RateDur; }
        else { total = job.Total; done = job.Down; speed = job.Speed; }
        if (total <= 0 || speed <= 0) return null;
        return Math.Max(0.0, total - done) / speed;
    }

    private static (double? eta, string note) JobEta(Job job)
    {
        string phase = string.IsNullOrEmpty(job.Phase) ? "下载" : job.Phase;
        if (phase == "封装" || phase == "校验")
            return (job.EtaFixed > 0 ? (double?)job.EtaFixed : null, "");
        if (job.Eta.HasValue) return (job.Eta, "");
        // 速率暂不可测 → 用「最近一次有效速率」兜底
        double rate, total, done;
        if (job.Unit == "dur") { rate = job.Meter.LastSpeed; total = job.TotalDur; done = job.DoneDur; }
        else { rate = job.Bmeter.LastSpeed; total = job.Total; done = job.Down; }
        if (rate <= 0 || total <= 0) return (null, "");
        return (Math.Max(0.0, total - done) / rate, "");
    }

    private static double EstimateMuxSeconds(Job job)
    {
        double secs = job.Total > 0 ? job.Total / MuxDiskSpeed : 0.0;  // 按 10MB/s 写速
        secs += (job.Lesson?.Duration ?? 0) / 60.0;                    // ffmpeg 约 60x 实时
        secs += 3.0;                                                    // ffprobe 校验
        return Math.Max(3.0, secs);
    }

    private void RefreshTaskRow(Job job)
    {
        var tr = job.TaskRow;
        if (tr == null || job.Finished) return;   // 已结束不覆盖「用时 …」
        // 阶段守卫白名单 = 全部进行中阶段
        string pt = States.PhaseWord(job.Phase);
        if (!string.IsNullOrEmpty(pt) && States.IsRunningWord(tr.StateWord))
            tr.StateWord = pt;
        if (job.Total > 0 && (job.Phase == "下载" || job.Phase == "封装" || job.Phase == "校验"))
            tr.Size = (job.Down / 1048576.0).ToString("0.0") + "/" +
                      (job.Total / 1048576.0).ToString("0") + " MB";
        else if (!string.IsNullOrEmpty(job.OutPath) && File.Exists(job.OutPath))
            tr.Size = (new FileInfo(job.OutPath).Length / 1048576.0).ToString("0.0") + " MB";
        tr.Speed = Util.FmtSpeed(job.Speed);
        var (eta, note) = JobEta(job);
        string txt = eta.HasValue ? Util.FmtDur(eta.Value) : "--";
        if (!string.IsNullOrEmpty(note)) txt += " " + note;
        tr.Eta = txt;
        tr.Progress = job.Percent();
    }

    private void RefreshAllTaskRows()
    {
        foreach (var id in _runningWorkers.ToList())
        {
            var job = GetJob(id);
            if (job != null) RefreshTaskRow(job);
        }
    }

    private void TickEta()
    {
        if (_runningWorkers.Count == 0 && _pendingQueue.Count == 0)
        {
            if (LblTaskEta.Text.Length > 0) LblTaskEta.Text = "";
            return;
        }
        // 暂停时冻结倒计时：不重算速率 / ETA
        if (!_paused)
        {
            foreach (var id in _runningWorkers.ToList())
            {
                var job = GetJob(id);
                if (job == null) continue;
                job.Speed = job.Bmeter.Speed();
                job.RateDur = job.Unit == "dur" ? job.Meter.Speed() : job.Speed;
                job.Eta = ComputeEta(job);
            }
        }
        RefreshAllTaskRows();
        UpdateGlobalEta();
    }

    private void UpdateGlobalEta()
    {
        double totalEta = 0;
        int nRun = 0;
        int nWait = _pendingQueue.Count;
        foreach (var id in _runningWorkers)
        {
            var job = GetJob(id);
            if (job == null) continue;
            nRun++;
            var (eta, _) = JobEta(job);
            if (eta.HasValue) totalEta += eta.Value;
        }
        // 排队任务按实测「内容速率」折算
        var rates = new List<double>();
        foreach (var id in _runningWorkers)
        {
            if (_networkReleased.Contains(id)) continue;   // 封装中的不产生下载速率
            var job = GetJob(id);
            if (job != null && job.Unit == "dur" && job.RateDur > 0) rates.Add(job.RateDur);
        }
        if (rates.Count > 0 && nWait > 0)
        {
            double rate = rates.Average();
            foreach (var j in _pendingQueue) totalEta += (j.Lesson?.Duration ?? 0) / rate;
        }
        if (nRun == 0 && nWait == 0) { LblTaskEta.Text = ""; return; }
        int nLocal = _networkReleased.Count(id => _runningWorkers.Contains(id));
        LblTaskEta.Text = "剩余约 " + Util.FmtDur(totalEta) + " · " +
                          (nRun - nLocal) + " 下载 / " + nLocal + " 封装 · " + nWait + " 个排队";
    }

    // ══════════════════════ 三处状态一致 / 终态守卫 ══════════════════════
    private LessonRow RowOfLesson(Lesson le)
    {
        if (le == null) return null;
        return _lessonRows.FirstOrDefault(r => ReferenceEquals(r.Lesson, le));
    }

    private static void SetRowState(LessonRow row, string word, string msg)
    {
        row.StateWord = word;
        if (!string.IsNullOrEmpty(msg)) row.ToolTip = msg;
    }

    private void SetBothStates(Job job, string word, string msg = null, bool force = false)
    {
        var tr = job.TaskRow;
        // ★ 终态守卫：任务已结束且状态列已是终态 → 迟到的阶段信号不许覆盖。
        //   force=True 用于写入终态本身（完成/失败回调）。
        if (!force && job.Finished && tr != null && !States.IsRunningWord(tr.StateWord)) return;
        var row = RowOfLesson(job.Lesson);
        if (row != null) SetRowState(row, word, msg);
        if (tr != null) tr.StateWord = word;
    }

    // ══════════════════════ 下载管理表 ══════════════════════
    private TaskRow FindTaskRow(string outPath)
    {
        if (string.IsNullOrEmpty(outPath)) return null;
        return _taskRows.FirstOrDefault(t =>
            string.Equals(t.OutPath, outPath, StringComparison.OrdinalIgnoreCase));
    }

    private TaskRow EnsureTaskRow(Job job, string state)
    {
        var tr = FindTaskRow(job.OutPath);
        if (tr == null) { tr = new TaskRow(); _taskRows.Add(tr); }
        tr.OutPath = job.OutPath;
        tr.ToolTip = job.OutPath;
        tr.JobId = job.JobId;
        tr.Title = job.Lesson?.Title ?? "";
        tr.StateWord = state;
        tr.Size = "";
        tr.Speed = "--";
        tr.Eta = "--";
        tr.Progress = 0;
        job.TaskRow = tr;
        RecordHistory(job.OutPath, tr.Title, job.Camp?.Name ?? "", state,
            duration: (long)(job.Lesson?.Duration ?? 0));
        FlushHistory();
        return tr;
    }

    private void UpdateTaskFinished(Job job, string state, string msg)
    {
        var tr = job.TaskRow;
        if (tr == null) return;
        tr.StateWord = state;
        string path = job.Lesson?.OutPath ?? job.OutPath;
        long size = 0;
        if (!string.IsNullOrEmpty(path) && File.Exists(path))
        {
            try { size = new FileInfo(path).Length; } catch { }
            tr.Size = (size / 1048576.0).ToString("0.0") + " MB";
            tr.OutPath = path;
            tr.ToolTip = path;
        }
        tr.Speed = "--";
        tr.Eta = "用时 " + Util.FmtDur(Now() - job.T0);
        if (state == States.WordDone) tr.Progress = 100;
        RecordHistory(path, job.Lesson?.Title ?? "", job.Camp?.Name ?? "", state,
            job.Down, job.Total, job.DoneDur, job.TotalDur,
            (long)(job.Lesson?.Duration ?? 0), size);
        FlushHistory();
    }

    private void RestoreHistoryTasks()
    {
        if (_history.Count == 0) return;
        foreach (var rec in Services.History.Sort(_history))
        {
            string path = rec.path ?? "";
            if (path.Length == 0) continue;
            string state = rec.state ?? "";
            var tr = new TaskRow
            {
                OutPath = path,
                ToolTip = path,
                Title = string.IsNullOrEmpty(rec.title) ? Path.GetFileName(path) : rec.title,
                Speed = "--",
                Eta = "--",
                Size = "",
            };
            var pp = Services.History.PartsProgress(Services.History.PartsDirFor(path));
            long cached = pp.Bytes;
            tr.StateWord = state == States.WordDone ? States.WordDone
                : state == States.WordFailed ? States.WordFailed
                : cached > 0 ? "未完成（可续传）" : "未完成";
            long down = rec.down, total = rec.total;
            if (cached > 0) down = cached;
            if (total > 0)
            {
                tr.Size = (down / 1048576.0).ToString("0.0") + "/" +
                          (total / 1048576.0).ToString("0") + " MB";
                tr.Progress = Math.Max(0, Math.Min(100, (int)(down * 100.0 / total)));
            }
            else if (rec.size > 0)
                tr.Size = (rec.size / 1048576.0).ToString("0.0") + " MB";
            _taskRows.Add(tr);    // ★ 恢复的行默认不勾选（无选中项）
        }
        Log("已恢复上次下载列表：" + _taskRows.Count + " 条记录。");
    }

    // ══════════════════════ 历史 ══════════════════════
    private void RecordHistory(string path, string title, string camp, string state,
        long down = 0, long total = 0, double doneDur = 0, double totalDur = 0,
        long duration = 0, long size = 0)
    {
        if (string.IsNullOrEmpty(path)) return;
        var rec = HistoryRecord.Make(path, title, camp, state, size, down, total,
            doneDur, totalDur, duration);
        Services.History.Merge(_history, rec);
    }

    private void FlushHistory()
    {
        try { Services.History.Save(Services.History.Sort(_history)); }
        catch (Exception e) { Log("保存下载历史失败：" + e.Message); }
    }

    // ══════════════════════ 暂停 / 继续 ══════════════════════
    private void TogglePause()
    {
        _paused = !_paused;
        _control.Paused = _paused;         // 所有下载线程共用一个控制器（协作式）
        if (_paused)
        {
            BtnPause.Content = "继续";
            BtnPause.Style = (Style)FindResource("PrimaryButtonStyle");
            Log("已暂停所有下载（已下好的分片会保留，点「继续」接着下）。");
            SetAllRunningState(States.WordPaused);
        }
        else
        {
            BtnPause.Content = "暂停";
            BtnPause.Style = (Style)FindResource("PauseButtonStyle");
            Log("已继续下载。");
            ResumeStates();
            PumpQueue();
        }
    }

    private void ResumeStates()
    {
        foreach (var id in _runningWorkers.ToList())
        {
            var job = GetJob(id);
            if (job == null) continue;
            string word = States.PhaseWord(job.Phase);
            if (string.IsNullOrEmpty(word)) word = States.PhaseWord("下载");
            var row = RowOfLesson(job.Lesson);
            if (row != null) SetRowState(row, word, null);
            if (job.TaskRow != null) job.TaskRow.StateWord = word;
        }
        foreach (var job in _pendingQueue)
        {
            var row = RowOfLesson(job.Lesson);
            if (row != null) SetRowState(row, States.WordQueued, null);
        }
    }

    private void SetAllRunningState(string state)
    {
        foreach (var id in _runningWorkers.ToList())
        {
            var job = GetJob(id);
            if (job == null) continue;
            var row = RowOfLesson(job.Lesson);
            if (row != null) SetRowState(row, state, null);
            if (job.TaskRow != null) job.TaskRow.StateWord = state;
        }
        string queued = state == States.WordPaused ? States.WordPaused : States.WordQueued;
        foreach (var job in _pendingQueue)
        {
            var row = RowOfLesson(job.Lesson);
            if (row != null) SetRowState(row, queued, null);
        }
    }

    private void SyncPauseButton()
    {
        bool busy = _runningWorkers.Count > 0 || _pendingQueue.Count > 0;
        BtnPause.IsEnabled = busy;
        if (!busy && _paused)
        {
            _paused = false;
            _control.Paused = false;
            BtnPause.Content = "暂停";
            BtnPause.Style = (Style)FindResource("PauseButtonStyle");
        }
    }

    // ══════════════════════ 管理 / 配置 / 日志 ══════════════════════
    private void ClearTaskList()
    {
        _taskRows.Clear();
        _history.Clear();
        FlushHistory();
        Log("已清除下载列表（文件保留，历史记录已清）。");
    }

    private void DeleteTaskFiles()
    {
        var sel = LstTasks.SelectedItems.Cast<TaskRow>().ToList();
        if (sel.Count == 0)
        {
            MessageBox.Show(this, "请先选中要删除的任务。", "提示");
            return;
        }
        var ans = MessageBox.Show(this,
            "将删除 " + sel.Count + " 个成品文件。\n\n文件会先移到「_已删除」子目录，确认？",
            "删除文件", MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.No);
        if (ans != MessageBoxResult.Yes) return;

        string trash = Path.Combine(Root, "_已删除");
        int moved = 0;
        foreach (var tr in sel)
        {
            string path = tr.OutPath;
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) continue;
            try
            {
                Directory.CreateDirectory(trash);
                string baseName = Path.GetFileName(path);
                string stem = Path.GetFileNameWithoutExtension(path);
                string ext = Path.GetExtension(path);
                string target = Path.Combine(trash, baseName);
                int k = 1;
                while (File.Exists(target))
                    target = Path.Combine(trash, stem + "-" + (k++) + ext);
                File.Move(path, target);
                moved++;
            }
            catch (Exception e) { Log("删除失败 " + path + "：" + e.Message); }
        }
        _taskRows.Clear();
        _history.Clear();
        FlushHistory();
        Log("已移动 " + moved + " 个文件到 " + trash);
        MessageBox.Show(this, "已移动 " + moved + " 个文件。", "完成",
            MessageBoxButton.OK, MessageBoxImage.Information);
    }

    private void SyncChecker()
    {
        string root = Root;
        if (!string.Equals(root, _checkerRoot, StringComparison.OrdinalIgnoreCase))
        {
            _checkerRoot = root;
            _checker = Services.CreateChecker(root);
        }
    }

    private void SaveCfg()
    {
        string newDir = EdOut.Text.Trim();
        bool changed = !string.Equals(newDir, _outDir, StringComparison.OrdinalIgnoreCase);
        _outDir = newDir.Length > 0 ? newDir : _outDir;
        _quality = CmbQuality.SelectedIndex == 1 ? "720" : "max";
        _cfg.out_dir = _outDir;
        _cfg.quality = _quality;
        _cfg.platform = _platformId;
        _cfg.auto_launch = ChkAutoLaunch.IsChecked == true;
        _cfg.auto_close = ChkAutoClose.IsChecked == true;
        Config.Save(_cfg);

        if (_lessonGroups.Count > 0)
        {
            int n = _lessonRows.Count;
            LblLessonsHint.Text = _lessonGroups.Count == 1
                ? "共 " + n + " 节 · 目录：" + Path.Combine(_outDir, Naming.CampFolder(_lessonGroups[0].Camp.Name))
                : "共 " + n + " 节 · " + _lessonGroups.Count + " 个营 · 各自存到下载目录下的同名文件夹";
        }
        if (changed)
        {
            SyncChecker();
            _checker.Invalidate("");
            ScanExisting();
        }
    }

    private void Log(string text)
    {
        string line = "[" + DateTime.Now.ToString("HH:mm:ss") + "] " + text;
        AppendLogLine(line);
        StatusLabel.Text = text;        // 普通 log 会更新底部状态栏
        LogToFile(line);
    }

    private void LogState(string text)
    {
        // 阶段日志：只写日志框和文件，不抢底部状态栏
        string line = "[" + DateTime.Now.ToString("HH:mm:ss") + "] " + text;
        AppendLogLine(line);
        LogToFile(line);
    }

    private void AppendLogLine(string line)
    {
        TxtLog.AppendText(line + "\n");
        TxtLog.ScrollToEnd();
        if (TxtLog.LineCount > 2000)
        {
            var arr = TxtLog.Text.Split('\n');
            TxtLog.Text = string.Join("\n", arr.Skip(Math.Max(0, arr.Length - 1500)));
            TxtLog.ScrollToEnd();
        }
    }

    private static void LogToFile(string line)
    {
        var f = Environment.GetEnvironmentVariable("XQD_LOG_FILE");
        if (string.IsNullOrWhiteSpace(f)) return;
        try { File.AppendAllText(f.Trim(), line + "\n", new UTF8Encoding(false)); }
        catch { /* ignore */ }
    }

    private static string FirstLine(string s)
    {
        var t = (s ?? "");
        int i = t.IndexOfAny(new[] { '\r', '\n' });
        return i < 0 ? t : t.Substring(0, i);
    }

    private static T FindAncestor<T>(DependencyObject cur) where T : DependencyObject
    {
        while (cur != null)
        {
            if (cur is T t) return t;
            cur = VisualTreeHelper.GetParent(cur);
        }
        return null;
    }

    private void AdjustColumnWidths()
    {
        AdjustOne(LstLessons, States.ColTitle);
        AdjustOne(LstTasks, States.TaskColTitle);
    }

    private static void AdjustOne(ListView lv, int titleCol)
    {
        var gv = lv.View as GridView;
        if (gv == null || lv.ActualWidth <= 0 || titleCol >= gv.Columns.Count) return;
        double other = 0;
        for (int i = 0; i < gv.Columns.Count; i++)
            if (i != titleCol) other += gv.Columns[i].Width;
        double w = lv.ActualWidth - other - 36;
        if (w > 160) gv.Columns[titleCol].Width = w;
    }

    protected override void OnClosing(System.ComponentModel.CancelEventArgs e)
    {
        if (_pendingQueue.Count > 0)
        {
            Log("关闭中：取消 " + _pendingQueue.Count + " 个排队未开始的下载任务。");
            _pendingQueue.Clear();
        }
        _control.Paused = false;        // 解除暂停，避免下载线程永远等下去
        _control.Cancelled = true;
        _appCts.Cancel();
        try { FlushHistory(); SaveCfg(); } catch { }
        base.OnClosing(e);
    }

    // ══════════════════════ XAML 事件 ══════════════════════
    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Q && (Keyboard.Modifiers & ModifierKeys.Control) == ModifierKeys.Control)
        {
            e.Handled = true;
            Close();
        }
    }

    private void Window_SizeChanged(object sender, SizeChangedEventArgs e) => AdjustColumnWidths();

    private void BrandBox_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        var dlg = new HelpAboutWindow(this);
        dlg.ShowDialog();
    }

    private void BtnBrowse_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var dlg = new Microsoft.Win32.OpenFolderDialog();
            dlg.Title = "选择下载目录";
            // 用最小 API 集（Title / ShowDialog(Window) / FolderName），避免依赖可选属性。
            if (dlg.ShowDialog(this) == true && !string.IsNullOrEmpty(dlg.FolderName))
            {
                EdOut.Text = dlg.FolderName;
                SaveCfg();
            }
        }
        catch (Exception ex) { Log("选择目录失败：" + ex.Message); }
    }

    private void EdOut_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) SaveCfg();   // 回车也保存下载目录
    }

    private void BtnRetry_Click(object sender, RoutedEventArgs e) => _ = AutoCheckAuthAsync(true);

    private void TabList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (TabList.SelectedItem is string s && s != _selectedTab)
        {
            _selectedTab = s;
            _ = LoadCampsAsync();
        }
    }

    private void ChkAllCamps_Click(object sender, RoutedEventArgs e)
    {
        if (_campUpdating) return;
        bool want = _campHeaderState != "all";
        _campUpdating = true;
        foreach (var it in _campItems) it.SetCheckedSilently(want);
        _campUpdating = false;
        SyncAllCampsCheckbox();
        ScheduleRebuild();
    }

    private void LstCamps_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        int i = LstCamps.SelectedIndex;
        if (i >= 0 && i < _campItems.Count)
        {
            _currentCamp = _campItems[i].Camp;
            if (CheckedCamps().Count == 0) ScheduleRebuild();   // 一个都不勾时显示当前高亮营
        }
    }

    private void LstCamps_PreviewMouseUp(object sender, MouseButtonEventArgs e)
    {
        // 点营名文字 = 勾上（只增不减）；点在方框里交给 CheckBox 的双向绑定
        if (FindAncestor<CheckBox>(e.OriginalSource as DependencyObject) != null) return;
        var item = FindAncestor<ListBoxItem>(e.OriginalSource as DependencyObject);
        if (item?.DataContext is CampItem ci && !ci.IsChecked) ci.IsChecked = true;
    }

    private void BtnRefreshCamps_Click(object sender, RoutedEventArgs e) => _ = LoadCampsAsync();

    private void ChkLessonAll_Click(object sender, RoutedEventArgs e)
    {
        bool want = _lessonHeaderState != "all";
        SetAllLessonChecks(want);
        UpdateLessonHeaderState();
    }

    private void LstLessons_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (LstLessons.SelectedItem is LessonRow r) StartDownloads(new List<LessonRow> { r });
    }

    private void CmbQuality_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        _quality = CmbQuality.SelectedIndex == 1 ? "720" : "max";
    }

    private void BtnAll_Click(object sender, RoutedEventArgs e)
    {
        SetAllLessonChecks(true);
        UpdateLessonHeaderState();
    }

    private void BtnNone_Click(object sender, RoutedEventArgs e)
    {
        SetAllLessonChecks(false);
        UpdateLessonHeaderState();
    }

    private void BtnRescan_Click(object sender, RoutedEventArgs e) => RescanExisting();

    private void BtnDownload_Click(object sender, RoutedEventArgs e) => StartDownloadSelected();

    private void BtnPause_Click(object sender, RoutedEventArgs e) => TogglePause();

    private void BtnDownloadOne_Click(object sender, RoutedEventArgs e)
    {
        if (LstLessons.SelectedItem is LessonRow r) StartDownloads(new List<LessonRow> { r });
        else MessageBox.Show(this, "请先选中一节课。", "提示");
    }

    private void BtnClearList_Click(object sender, RoutedEventArgs e) => ClearTaskList();

    private void BtnDeleteFiles_Click(object sender, RoutedEventArgs e) => DeleteTaskFiles();

    private void BtnClearLog_Click(object sender, RoutedEventArgs e) => TxtLog.Clear();
}
