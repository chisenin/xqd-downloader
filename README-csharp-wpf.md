# 兴趣岛课程导出工具 · C# / WPF 版

> **v1.5.3 起两套实现合并到同一个 `master` 分支**：C# / WPF 源码在 `src/`，
> Python / PySide6 源码在仓库根目录，二者功能对齐、同时发版。
> 本文是 **C# / WPF 实现的专门说明**；总览、发版流程与 Python 版说明见根目录
> [`README.md`](README.md)。旧 `csharp-wpf` 分支及 `v1.5.2*` Release 只作历史留存。
>
> ★ 打包/编译由 `.github/workflows/release.yml` 在 GitHub Actions 上完成，
> 单个 Release 同时提供 `xingqudao-downloader-vX.Y.Z.exe`（Python）与
> `xingqudao-downloader-vX.Y.Z.zip`（C#），本机不产出二进制。

把「兴趣岛」App（`com.qlchat.xingqudao`）中**已购买课程**的视频批量导出为通用 MP4，
用于在本地教学大屏上播放。DRM 课程走同目录下的明文孪生清单，**无需解密**。

> 用途是临时转移到教学大屏，看完及时删除（大屏磁盘空间有限）。
> 只处理自己有权访问与保存的内容，详见文末「合规与使用边界」。

---

## v1.5.2 补丁（2026-11-08）

- 修复营列表「全选」：点全选后下面各营的方框**立即全部勾上**，再点一次全部取消。
- 各营方框单独勾选 / 取消时，表头「全选」同步显示 **未勾 / 半勾 / 全勾** 三态。
- 课程列表的「全选 / 清空 / 表头勾选」是同一套机制，一并修好。
- 根因：`SetCheckedSilently()` 调用无参 `Raise()`，`[CallerMemberName]` 变成方法名
  `SetCheckedSilently`，WPF 的 TwoWay 绑定收不到 `IsChecked` 属性通知 →
  「数据已勾上、界面方框不动」。改为显式 `Raise(nameof(IsChecked))`，
  表头三态统一走 `States.CheckAllState(k, n)`。
- 回归：离线断言新增 K 组（直接编译 GUI 的 ViewModel 源码），合计 **224 项全绿**；
  另用真实 WPF 绑定跑了 **12 项** 双向联动实测，全部通过。

> **历史（v1.5.2）**：当时 C# 版在独立 Release `v1.5.2-csharp-wpf`，
> 附件 `xingqudao-downloader-csharp-v1.5.2.zip`；Python 版另有 Release `v1.5.2`。
> v1.5.3 起改为单个 Release 挂两个附件（见根目录 README）。
> 替换时把整个发布目录一起覆盖，不要只拷单个 exe。

---

## 能做什么

- 拉取**正式营 / 体验营**的营列表与课表。课名一次拿全，不靠播放反推。
- 并行分片下载 → 转封装 MP4 → ffprobe 校验时长。
- 自动跳过已下载的课，残缺文件清理后用规范名覆盖重下。
- 暂停 / 继续、跨会话断点续传、下载历史恢复、下载目录记忆。
- 桌面 GUI（v1.5.2 全功能）：多营勾选合并、标题前缀保留原营序号、重新载入仍显示真实进度、进入封装阶段即释放网络槽位并行下一节。
- 授权默认直接使用本机缓存，**平时启动不拉起 MuMu 模拟器**；点「重新授权」才刷新。子进程 Qt 环境已隔离，根治 MuMu 的 Qt 插件弹窗。
- DRM 课自动选择同目录的明文孪生，并**按时长校验**，避免下错内容。
- 两种数据源：`api`（默认，**下载过程不需要模拟器**）/ `adb`（旧路径，需 MuMu 桥接）。

三种前端都在：`Xqd.Gui` 桌面工具（日常使用）、`Xqd.Server` 本地网页版、`Xqd.Cli` 全量批处理。

---

## 快速开始

### 方式一：直接用发行包（推荐）

从 [GitHub Releases](https://github.com/chisenin/xqd-downloader/releases) 下载
`xingqudao-downloader-v1.5.3.zip`，**解压后把整目录一起拷贝**，
双击 `gui/xingqudao-downloader.exe` 即可，绿色免安装。

> 不要只拷单个 exe：同级目录里的 `Xqd.Core.dll`、`*.deps.json`、`*.runtimeconfig.json` 是必需的。
> 需要系统已安装 **.NET 8 桌面运行时**；ffmpeg / ffprobe 需在 PATH。

操作流程：首次点「重新授权」（仅首次需要 MuMu）→ 左栏选「正式营 / 体验营」→
**勾选一个或多个营**（表头可全选，营名「·」分隔滚动展示）→
合并后的课程列表勾选课程（或双击单行）→「下载选中」→ 需要时点「暂停 / 继续」。
第一列「标题前缀」是该课在**原营**里的序号（合并不重排），
一节进入封装后网络槽位立刻让给下一节。点顶栏标题区可打开「使用说明与关于」。

### 方式二：源码构建

```bash
dotnet build src/Xqd.sln -c Release
dotnet run --project src/Xqd.Gui -c Release
```

本机 SDK 装在 `D:\user\chisenin\.dotnet`（8.0.416，用户目录、未改系统），
构建时把 `dotnet` 换成绝对路径 `D:/user/chisenin/.dotnet/dotnet.exe` 即可。

### 方式三：本地网页版

```bash
dotnet dist-csharp/server/Xqd.Server.dll --port 8765 --mode api --out "D:/user/chisenin/Videos"
# 浏览器打开 http://127.0.0.1:8765/
```

`--mode` 可取 `api`（默认）或 `adb`。服务只绑定 `127.0.0.1`。
`api` 模式**不需要 sweep**，直接返回课表；轻课已确认为空，直接返回空列表、绝不探测。

### 方式四：CLI 全量批处理

```bash
dotnet dist-csharp/cli/Xqd.Cli.dll --out "Z:/太极营" --workers 2 \
    --seg-workers 12 --tabs 正式营,体验营 --quality max
```

可选参数：`--only`（只跑指定营/课）、`--quality max|720|1080`、
`--workers`（课程级并发）、`--seg-workers`（分片并发）、`--mode api|adb`。
断点状态写在 `state/batch_state.json`，重跑自动续跑。

---

## 环境要求

| 项 | 值 |
|---|---|
| 目标框架 | `net8.0`（Core / Server / CLI / Tests）、`net8.0-windows` + `UseWPF`（GUI） |
| SDK | .NET 8 SDK（本机 8.0.416） |
| 运行时 | 系统自带 `Microsoft.NETCore.App` + `Microsoft.WindowsDesktop.App` 8.x（本机 8.0.22） |
| 外部包 | **零 NuGet 依赖**，全部只用 BCL（System.Text.Json / HttpClient / Process / WPF） |
| 外部工具 | ffmpeg / ffprobe（与 Python 版相同，PATH 或引擎的固定回退目录） |
| 授权 | 首次需 MuMu 模拟器读取本机登录态；之后直接用缓存，`api` 模式下载本身不依赖模拟器 / ADB |

★ 业务网关与 CDN 请求**必须禁用系统代理**，否则会被代理吞掉返回 HTML；
成功码在 `state.code`，不是顶层 `code`。

---

## 解决方案结构

```
src/Xqd.sln
├── Xqd.Core/          公共契约 + 全部业务能力（类库）
│   ├── Models.cs / States.cs / Naming.cs / Config.cs / Creds.cs
│   ├── Net.cs / Proc.cs / Util.cs / Contracts.cs
│   ├── Api/            业务网关、平台适配、ApiCompat
│   ├── Auth/           MuMu 免 adbd 授权
│   ├── Engine/         清单分派、DRM 孪生、抽样、并发分片、转封装
│   ├── History/        下载历史与跨会话续传
│   ├── Dedupe/         已下载检测
│   ├── Adb/            ADB 采集 / uiautomator DOM / sweep
│   └── Crypto/         163 解密内核（非 MIT，见 NOTICE）
├── Xqd.Gui/           WPF 桌面工具（XAML + code-behind + 控件 + VM）
├── Xqd.Server/        HttpListener 本地网页版（复用根目录 ui.html）
├── Xqd.Cli/           全量批处理
└── Xqd.Tests/         离线回归（224 项）
```

前端**只经 `Services.*`** 取实现（`CreatePlatform` / `CreateDataSource` / `Engine` /
`History` / `Auth` / `CreateChecker`），不直接依赖具体类。

### 与 Python 实现的模块对照

| Python（根目录） | C#（`src/`） |
|---|---|
| `xqd_platform.py` / `xqd_api.py` | `Xqd.Core/Api/{QianliaoClient,QianliaoPlatform,ApiCompat}.cs` |
| `xqd_engine.py` | `Xqd.Core/Engine/*.cs` |
| `xqd_auth.py` / `xqd_creds.py` / `xqd_proc.py` | `Xqd.Core/Auth/MumuAuth.cs` + 公共 `Creds.cs` / `Proc.cs` |
| `xqd_history.py` / `xqd_dedupe.py` | `Xqd.Core/History/HistoryStore.cs` / `Dedupe/ExistingChecker.cs` |
| `xqd_gui.py` | `Xqd.Gui/*` |
| `xqd_server.py` + `ui.html` | `Xqd.Server/*` + 复用的 `ui.html` |
| `xqd_batch.py` / `xqd_pdl.py` | `Xqd.Cli/*` |
| `xqd.py` / `xqd_app.py` | `Xqd.Core/Adb/*.cs` |
| `_lel/core/netease_mooc.py` | `Xqd.Core/Crypto/Netease163.cs` |
| `build_exe.py`（PyInstaller） | `dotnet publish` |

---

## 保持不变的关键契约

- **单一事实来源**：`States.cs`（状态词 / 配色 / 列号 / 槽位常量）、`Naming.cs`
  （`<序号>.<课名>.<YYYY.MM.DD>.mp4`）、`Config.cs`（目录记忆 / 注册表 Known Folder GUID /
  测试隔离）、`Contracts.cs`（所有前端共用的接口）。
- **少请求**：调用方现场解析的 `PlayUrl` 直接传给引擎，不重复 resolve；
  `api` 模式不 sweep；轻课直接返回空，不探测。
- **续传**：`%05d_<basename>` 分片命名、成功才清分片、清理条件
  `if (ownDir || (ok && !keepParts))`；失败/中止必须保留分片。
- **三处状态一致**：课名后状态词 / 下载管理状态列 / 运行日志共用 `States` 词表，
  终态守卫 + 阶段白名单含全部进行中阶段。
- **两个独立速率计**：字节速率给「速度」列，内容时长速率给 ETA，不能混用。
- 凭据只从 `XQD_COOKIE` 环境变量或 `%USERPROFILE%\.xqd_tool\cookie.txt` 读取，
  **代码里绝不硬编码**；`XQD_TEST_HOME` 只隔离配置 / 历史 / 分片，不影响凭据读取。

---

## 输出结构

```
<下载目录>\<营名>\<序号>.<课名>.<YYYY.MM.DD>.mp4

例：Z:\太极营\道德经诵读\1.《道德经》一至三章.2026.07.27.mp4
```

- 序号 = 营内课表顺序（从 1 起，与 App 列表一致）
- 日期 = 该节课的 `startTime`；课名里的全角冒号 `：` 原样保留
- 音频课保留原始容器（`.mp3` / `.m4a`），不强行塞进 MP4
- 命名规则的唯一事实来源是 `Xqd.Core/Naming.cs`

---

## 构建、发布与回归

```bash
DOTNET="D:/user/chisenin/.dotnet/dotnet.exe"   # 或直接用 dotnet

"$DOTNET" build src/Xqd.sln -c Release
"$DOTNET" run --project src/Xqd.Tests -c Release       # 224 项离线回归

"$DOTNET" publish src/Xqd.Gui/Xqd.Gui.csproj    -c Release -o dist-csharp/gui    --self-contained false
"$DOTNET" publish src/Xqd.Server/Xqd.Server.csproj -c Release -o dist-csharp/server --self-contained false
"$DOTNET" publish src/Xqd.Cli/Xqd.Cli.csproj    -c Release -o dist-csharp/cli    --self-contained false
```

★ `PublishSingleFile=true` 会触发 `Microsoft.NET.ILLink.Tasks` 的 NuGet 还原，
离线环境报 NU1100，因此采用普通目录发布（每个前端约 0.5 MB，共用系统 .NET 8 运行时）。

回归测试**不发网络请求、不启动模拟器、不需要有效 Cookie**，
但 `XQD_TEST_HOME` 仍用于隔离配置 / 历史 / 分片缓存。

---

## 验证结果

- Release 编译 **0 错误 / 0 警告**；离线回归 **224 项全绿**。
- WPF 实机启动确认窗口标题「兴趣岛视频下载器 v1.5.1」、进程响应正常、无未处理异常。
- 本地服务 `/api/state`、`/`（`ui.html` 16.6 KB）、`/api/camps?tab=轻课`（空）已实跑通过；
  CLI `--help` 在原生 Windows 控制台中文正常。
- ⚠️ **未做真网络全量下载**（网络不稳定、流量昂贵，且 master 已端到端验证过 6/6）；
  下载链路的行为由离线断言 + 与 Python 版逐行对照保证。

---

## 已知约束与取舍

- 转封装用**按序 cat 字节拼接**，不要用 ffmpeg concat demuxer
  （后者会重置时间戳，实测成品长 6 秒）。
- 分片临时目录要**逐个删**：批量删除会触发安全删除阈值被拦，导致目录累积。
- 封装 / 校验阶段不发任何网络请求（GUI 靠这个释放网络槽位）。
- 改过业务层后必须重启本地服务。
- 网络不稳定、流量昂贵：抽样片写盘复用，续传优先读本地缓存，已下载自动跳过。
- 课程内容导出后请及时删除，不要长期留存。

---

## 文档索引

**动手改代码前先读 `docs/01`，能省掉大量重复探测。**

| 文件 | 内容 |
|---|---|
| [`01-已验证事实.md`](docs/01-已验证事实.md) | ⭐ 权威结论清单，所有已实测确认的事实 |
| [`03-踩坑与修复记录.md`](docs/03-踩坑与修复记录.md) | 实际浪费过时间的坑 |
| [`09-兴趣岛业务API.md`](docs/09-兴趣岛业务API.md) | 业务网关契约（端点 / 参数 / 成功码） |
| [`10-GUI工具说明.md`](docs/10-GUI工具说明.md) | 界面、状态、ETA、历史、回归清单（Python 版，规格同样适用） |
| [`11-工具实现要点.md`](docs/11-工具实现要点.md) | 授权 / MuMu / 速率 / 状态 / 续传 / 测试隔离 |
| [`12-项目现状与合规.md`](docs/12-项目现状与合规.md) | 代码结构、环境、合规声明 |
| [`RELEASE_NOTES.md`](RELEASE_NOTES.md) | 本分支发行说明（Release 正文） |

---

## 合规与使用边界

- 本分支运行时主链路为独立编写，不含任何账号体系、加密服务或商业客户端代码，
  也不含任何账号凭据（凭据只在运行时从环境变量或用户私有文件读取）。
- `Xqd.Core/Crypto/Netease163.cs` 属于对第三方客户端行为的独立复现记录，
  **不在其上游仓库的 MIT 授权范围内**，不得声称 MIT。完整声明见 [`NOTICE.md`](NOTICE.md) 第五节。
- 课程内容的权利不因本软件改变。请**只处理自己已购买、有权访问与保存的内容**，
  本工具不提供、也不鼓励用于未购内容的批量获取；仅供个人学习与本地教学使用。
