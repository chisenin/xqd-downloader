using System;
using System.Collections.Generic;

namespace Xqd.Server;

/// <summary>
/// 后台任务 —— 对应 Python xqd_server.py 的 STATE['tasks'] 元素。
/// 字段名在 Snapshot() 里映射成 Python 版 JSON 键（小写 / 下划线）。
/// </summary>
public sealed class TaskItem
{
    public int Id;
    public string Kind = "";
    public string Title = "";
    public string Detail = "";
    public string State = "running";       // running | done | error
    public double Progress;
    public string Current = "";
    public int Ok;
    public int Fail;
    public int Skip;
    public readonly List<string> Log = new();
    public double Started;
    public double Finished;

    public Dictionary<string, object> Snapshot() => new()
    {
        ["id"] = Id,
        ["kind"] = Kind,
        ["title"] = Title,
        ["detail"] = Detail,
        ["state"] = State,
        ["progress"] = Progress,
        ["current"] = Current,
        ["ok"] = Ok,
        ["fail"] = Fail,
        ["skip"] = Skip,
        ["log"] = new List<string>(Log),
        ["started"] = Started,
        ["finished"] = Finished,
    };
}

/// <summary>
/// 全局状态 + 任务状态机 —— 对应 Python 的 LOCK / STATE / TASK_SEQ /
/// new_task / task_log / finish_task。所有成员一律在 _lock 内访问，线程安全。
/// </summary>
public sealed class ServerState
{
    private readonly object _lock = new();
    private int _seq;
    private int _busy;
    private readonly List<TaskItem> _tasks = new();

    public bool AdbConnected;
    public bool AdbBusy;
    public string OutRoot = "";
    public string LastError = "";
    public string Mode = "api";

    public ServerState(string outRoot, string mode)
    {
        OutRoot = outRoot;
        Mode = mode;
        // Python main() 在 adb 模式启动即 ensure_connected()；这里只记录连接态，
        // 不主动启动模拟器（避免启动期副作用），实际连接由业务动作惰性完成。
        AdbConnected = mode == "adb";
    }

    /// <summary>new_task(kind, title, detail)：任务 id 自增，最新任务插到最前，最多留 40 个。</summary>
    public TaskItem NewTask(string kind, string title, string detail = "")
    {
        lock (_lock)
        {
            var t = new TaskItem
            {
                Id = ++_seq,
                Kind = kind,
                Title = title,
                Detail = detail,
                Started = Epoch(),
            };
            _tasks.Insert(0, t);
            if (_tasks.Count > 40)
                _tasks.RemoveRange(40, _tasks.Count - 40);
            return t;
        }
    }

    /// <summary>task_log：追加 "HH:MM:SS msg"，同时打印到控制台（等价 A.log）。</summary>
    public void TaskLog(TaskItem t, string msg)
    {
        lock (_lock)
        {
            t.Log.Add(Stamp() + " " + msg);
            // 保留最近 200 条；Python 的 del log[-200:] 是笔误，会把新日志删光。
            if (t.Log.Count > 200)
                t.Log.RemoveRange(0, t.Log.Count - 200);
        }
        Console.WriteLine("[" + Stamp() + "] " + msg);
    }

    /// <summary>在锁内就地更新任务字段（progress / current / 计数等）。</summary>
    public void Update(TaskItem t, Action<TaskItem> apply)
    {
        lock (_lock) apply(t);
    }

    /// <summary>finish_task：done 时把 progress 置 100，error 保持当前进度。</summary>
    public void FinishTask(TaskItem t, string state = "done")
    {
        lock (_lock)
        {
            t.State = state;
            t.Finished = Epoch();
            if (state == "done") t.Progress = 100.0;
        }
    }

    public void SetError(string text) { lock (_lock) LastError = text ?? ""; }
    public void SetOutRoot(string path) { lock (_lock) OutRoot = path; }
    public string CurrentOutRoot() { lock (_lock) return OutRoot; }

    /// <summary>adb_busy：是否正有任务占用数据源（等价 Python 的 adb_guard）。</summary>
    public void EnterBusy()
    {
        lock (_lock) { _busy++; AdbBusy = true; }
    }

    public void LeaveBusy()
    {
        lock (_lock) { _busy = Math.Max(0, _busy - 1); AdbBusy = _busy > 0; }
    }

    /// <summary>/api/state 的响应体，字段名与 Python 版完全一致。</summary>
    public Dictionary<string, object> Snapshot()
    {
        lock (_lock)
        {
            var list = new List<Dictionary<string, object>>();
            for (int i = 0; i < _tasks.Count && i < 12; i++)
                list.Add(_tasks[i].Snapshot());
            return new Dictionary<string, object>
            {
                ["adb_connected"] = AdbConnected,
                ["adb_busy"] = AdbBusy,
                ["out_root"] = OutRoot,
                ["tasks"] = list,
                ["last_error"] = LastError,
                ["mode"] = Mode,
            };
        }
    }

    public static double Epoch() =>
        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;

    public static string Stamp() => DateTime.Now.ToString("HH:mm:ss");

    public static string Tail(string s, int n)
    {
        s = s ?? "";
        return s.Length <= n ? s : s.Substring(s.Length - n);
    }
}
