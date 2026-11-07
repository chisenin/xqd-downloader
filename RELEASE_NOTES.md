# 兴趣岛视频下载器 v1.5.2 · C# / WPF 版

> 这是 `csharp-wpf` 分支的**独立发行版**：把 `master` 的全部功能从 Python 移植为 C# / WPF。
> Python / PySide6 版 v1.5.2 是同一仓库 `master` 分支的另一个 Release，
> 两者功能对齐、各自独立发布，按需二选一即可。
>
> ⚠️ 仅供个人将**自己已购**的课程备份到**自有设备**使用；导出后请及时删除。

## v1.5.2 补丁（2026-11-08）

- 修复营列表「全选」：点全选后下面各营的方框**立即全部勾上**，再点一次全部取消。
- 各营方框单独勾选 / 取消时，表头「全选」同步显示 **未勾 / 半勾 / 全勾** 三态。
- 课程列表的「全选 / 清空 / 表头勾选」是同一套机制，一并修好。
- 根因：`SetCheckedSilently()` 调用无参 `Raise()`，`[CallerMemberName]` 变成方法名
  `SetCheckedSilently`，WPF 的 TwoWay 绑定收不到 `IsChecked` 属性通知 →
  「数据已勾上、界面方框不动」。改为显式 `Raise(nameof(IsChecked))`，
  表头三态统一走 `States.CheckAllState(k, n)`；批量设置仍不发 `CheckChanged`，
  避免全选 9 个营触发 9 次课表重建。
- Python 版用 Qt 的 `item.setCheckState`，本来没有这个问题；该版本仅同步版本号到 1.5.2。

## 本版本内容

- 运行时主链路全部改为 C#（.NET 8），桌面界面由 PySide6 改为 **WPF**；**零第三方 NuGet 依赖**，只用 BCL。
- 解决方案共 5 个项目：`Xqd.Core` / `Xqd.Gui` / `Xqd.Server` / `Xqd.Cli` / `Xqd.Tests`，48 个源码文件、约 1.1 万行。
- 功能与 master v1.5.2 对齐：多营勾选与合并、6 列课程表（标题前缀保留原营内序号）、双速率计与 ETA、网络 + 封装双槽位流水线、暂停/继续、跨会话断点续传、进度恢复、已下载跳过、三处状态一致。
- 授权默认直接使用本机缓存，**平时启动不拉起 MuMu 模拟器**；只有首次或点「重新授权」才刷新。子进程 Qt 环境已净化，不再弹 MuMu 的「no Qt platform plugin」错误。
- 本地网页版与 CLI 全量批处理一并移植，接口、JSON 字段与命令行参数与 Python 版一致。
- 保留 `api`（默认，下载不需要模拟器）/ `adb`（旧路径，需 MuMu 桥接）两种数据源。

## 下载与校验

| 项 | 值 |
|---|---|
| 附件 | `xingqudao-downloader-csharp-v1.5.2.zip` |
| 大小 | 246,081 字节（约 241 KB，目录发布，含 7 个文件） |
| SHA-256 | `1fec997dff2c68c07a4e1c79e601dd1e12619428f574b0813d40d57ebba10589` |
| 运行依赖 | Windows 10/11 x64 + 系统已安装 **.NET 8 桌面运行时**（`Microsoft.WindowsDesktop.App 8.x`） |
| 外部工具 | ffmpeg / ffprobe（转封装与成品时长校验，需在 PATH 或引擎回退目录） |

★ **解压后请把整目录一起拷贝**，双击 `xingqudao-downloader.exe` 启动；
不要只拷单个 exe，同级目录里的 `Xqd.Core.dll`、`*.runtimeconfig.json` 等是必需的。
文件名保持纯 ASCII，避免 GitHub Releases 吞掉中文附件名。

## 使用

双击启动 → 首次点「重新授权」（仅首次需要 MuMu）→ 左栏勾选「正式营 / 体验营」→
可勾选多个营合并课表 → 在课程列表勾选课程（或双击单行）→「下载选中」。
顶栏可设置下载目录，点标题区打开「使用说明与关于」。

输出结构：`<下载目录>\<营名>\<序号>.<课名>.<YYYY.MM.DD>.mp4`。
详细说明见仓库 `README-csharp-wpf.md` 与 `docs/10-GUI工具说明.md`。

## 验证

- `dotnet build src/Xqd.sln -c Release`：**0 错误 / 0 警告**。
- 离线回归 **224 项全绿**（命名、状态词、格式、配置隔离、历史合并、去重、引擎分片与明文孪生、ADB DOM、API 契约、Qt 环境净化，以及 v1.5.2 新增 K 组 25 项联动断言）。
- 真实 WPF `CheckBox` + `Binding("IsChecked", TwoWay)` 实测 **12 项全绿**：全选 9 框齐勾、取消一个转半勾、勾回全勾、全不选 9 框齐清，课程行同机制。
- WPF 实机启动确认窗口标题「兴趣岛视频下载器  v1.5.2」、进程响应正常、无未处理异常；本地服务 `/api/state`、`/`（`ui.html`）、轻课空列表，以及 CLI `--help` 均已实跑通过。
- ⚠️ **未做真网络全量下载**（网络不稳定、流量昂贵；master 已端到端验证 6/6）。下载链路的行为由离线断言 + 与 Python 版逐行对照保证。

## 已知取舍

- `PublishSingleFile=true` 需要联网还原 `Microsoft.NET.ILLink.Tasks`（离线环境报 NU1100），因此采用 **framework-dependent 目录发布**：三个前端各约 0.5 MB，共用系统 .NET 8 运行时。
- 与 Python 版 96.5 MB 的单文件 exe 不同，本版需要先装 .NET 8 桌面运行时；换来的是体积从 96.5 MB 降到 241 KB，且不再需要 PyInstaller 与 Qt DLL 收集。
- 163 解密内核按第三方客户端行为独立复现，**不属于**学无止仓库的 MIT 授权范围，本工具整体不声明 MIT。

## 许可与合规

- 运行时主链路独立编写，不含账号体系、加密服务或商业客户端代码，也不含任何账号凭据。
- 组件：.NET 8 / WPF（MIT）· FFmpeg（LGPL-2.1+ / GPL，不随本仓库分发）· 学无止（参考，MIT）；完整声明见仓库 `NOTICE.md` 第五节。
- 课程内容的权利不因本软件改变。请**只处理自己已购买、有权访问与保存的内容**，本工具不提供、也不鼓励用于未购内容的批量获取。
