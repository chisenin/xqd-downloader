# xqd —— Python 核心库（只做想法验证）

**正式版本不在这里。** 交付给用户的是 `xqd-avalonia`（C# + Avalonia）打出来的
自包含单文件 exe，见 GitHub Releases；目标机器不需要装 .NET、不需要装 Python。

这个包存在的理由只有一个：**先把「下载这件事」的规则跑通，再搬进 C# Core**。

## 为什么 Python 退居二线

| 问题 | Python 版 | C# + Avalonia 版 |
|---|---|---|
| 换机器 | 要装 Python + 虚拟环境 + 依赖 | 下载一个 exe 双击即可 |
| 界面 | tkinter 糊出来的，缩放手感差 | 原生窗口，无边框 + 自绘热区 |
| 发版 | 需要打包解释器（体积大、杀软误报） | `dotnet publish` 出单文件，43 MB |
| 验证成本 | 改一行就能跑，**适合试想法** | 要编译，适合定型后实现 |

所以：**规则先用 Python 验证，定稿后 C# 必须同构实现**（两边函数名刻意对齐，
`naming.py` ↔ `Naming.cs`、`dedupe.py` ↔ `ExistingChecker.cs`，方便对照）。

## 模块

| 文件 | 对应 C# | 干什么 |
|---|---|---|
| `xqd/config.py` | `Config.cs` | 配置目录、下载目录（注册表 Known Folder）、配置读写、凭据 |
| `xqd/probe.py` | `Setup/ToolLocator.cs` | 探测 ffmpeg / MuMu / adb / 在线设备，点选结果记进 `tools.json` |
| `xqd/naming.py` | `Naming.cs` | 文件名规范（唯一事实来源，两边必须一致） |
| `xqd/dedupe.py` | `Dedupe/ExistingChecker.cs` | 已存在判定：主键 + 10 KB 门槛 + ffprobe 时长容差 max(3s,1%) |
| `xqd/mux.py` | `Engine/Muxer.cs` | 分片字节拼接 → `ffmpeg -c copy` 封装（不能用 concat demuxer） |
| `xqd/platform.py` | `Api/QianliaoClient.cs` | 业务网关：营列表 / 课表 / 播放地址（禁代理、认 `state.code`） |

## 怎么用

```bash
# 环境体检（缺什么、怎么补，都会打出来）
python tools/probe_env.py
python tools/probe_env.py --json

# 当库用
python -c "from xqd.platform import Platform; print(Platform().list_camps('正式营')[:3])"
```

零第三方依赖（纯标准库），Python 3.10+。

## 明确不做

- 不做完整 CLI、不做下载调度、不做 GUI；
- 不做回归测试套件（回归在 `xqd-csharp/src/Xqd.Tests`，281 项，CI 每次都跑）；
- 不参与发版。
