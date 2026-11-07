# 兴趣岛课程导出工具

> **当前分支是 `csharp-wpf`（C# / WPF 移植版）** —— 请看
> **[C# 分支 README](README-csharp-wpf.md)**（环境、构建、发布、模块对照、验证结果）。
> 本文件后半部分保留 `master` 分支的 Python 版说明，仅作对照；
> 本分支的发行说明见 [RELEASE_NOTES.md](RELEASE_NOTES.md)。

把「兴趣岛」App（`com.qlchat.xingqudao`）中**已购买课程**的视频批量导出为通用 MP4，
用于在本地教学大屏上播放。DRM 课程走同目录下的明文孪生清单，**无需解密**。

> 用途是临时转移到教学大屏，看完及时删除（大屏磁盘空间有限）。
> 本工具只处理自己有权访问与保存的内容，详见文末「合规与使用边界」。

---

## 能做什么

- 拉取**正式营 / 体验营**的营列表与课表。课名一次拿全，不靠播放反推。
- 并行分片下载 → 转封装 MP4 → ffprobe 校验时长；实测 16~32 并发约 8.4 MB/s，
  瓶颈在 CDN 而非本地磁盘。
- 自动跳过已下载的课，残缺文件清理后用规范名覆盖重下。
- 暂停 / 继续、跨会话断点续传、下载历史恢复、下载目录记忆。
- 桌面 GUI（v1.5.1）：多营勾选合并、标题前缀保留原营序号、
  重新载入仍显示真实进度、进入封装阶段即释放网络槽位并行下一节。
  平时启动**直接用已保存的授权、不用开模拟器**；点「重新授权」才刷新，
  子进程 Qt 环境已隔离（根治 MuMu 的 Qt 插件弹窗）。
- DRM 课自动选择同目录的明文孪生，并**按时长校验**，避免下错内容。
- 两种数据源：`api`（默认，**下载过程不需要模拟器**）/ `adb`（旧路径，需 MuMu 桥接）。

当前主要使用方式是桌面 GUI；网页版与 CLI 全量批处理仍然可用。

---

## 快速开始

### 方式一：桌面工具（日常使用）

打包好的单文件程序从 **GitHub Releases 附件**下载，双击即用、绿色免安装
（仓库尚未发布时，用 `python build_exe.py` 自行打包，见「打包与分发」）。

源码运行：

```bash
pip install PySide6-Essentials
python xqd_gui.py
```

操作流程：授权状态就绪 → 左栏选「正式营 / 体验营」→ **勾选一个或多个营**
（标题栏可全选，营名「·」分隔滚动展示）→ 合并后的课程列表里勾选课程
（或双击单行）→「下载选中」→ 需要时点「暂停 / 继续」。
第一列「标题前缀」是该课在**原营**里的序号（合并不重排），
「进度」列重新载入也保留真实进度；一节进入封装后网络槽位立刻让给下一节。
点顶栏标题区可打开「使用说明与关于」。

> 工具版本以 `xqd_gui.py` 里的 `APP_VERSION` 为准；界面细节见
> [`docs/10-GUI工具说明.md`](docs/10-GUI工具说明.md)。

### 方式二：本地网页版

```bash
python -u xqd_server.py --mode api --port 8765 --out "D:/user/chisenin/Videos"
# 浏览器打开 http://127.0.0.1:8765/
```

`--mode` 可取 `api`（默认）或 `adb`。服务请用后台任务方式启动，
用 `&` 会随 shell 退出被杀。改过业务层后**必须重启服务**。

### 方式三：CLI 全量批处理

```bash
python xqd_batch.py --out "Z:/太极营" --workers 2 --seg-workers 12 \
                    --tabs 正式营,体验营 --quality max
```

可选参数：`--only`（只跑指定营/课）、`--quality max|720|1080`、
`--workers`（课程级并发）、`--seg-workers`（分片并发）。
日常下载统一走 GUI；批处理入口主要用于无人值守的全量任务。

---

## 依赖

| 组件 | 用途 | 备注 |
|---|---|---|
| Python 3.8+ | 运行时 | 业务 HTTP / 服务 / 下载内核**只用标准库** |
| PySide6-Essentials | 桌面 GUI | 仅 GUI 与打包需要 |
| ffmpeg / ffprobe | 分片转封装、成品时长校验 | 需在 PATH，或放到引擎的查找路径 |
| pycryptodome | 网易云课堂(163) 地址解密内核 | 仅 `_lel/core/netease_mooc.py`，兴趣岛主链路不需要 |
| MuMu 模拟器 | 读取本机登录态以完成授权 | `api` 模式**下载本身不依赖模拟器/ADB** |

★ 业务网关与 CDN 请求必须 `ProxyHandler({})` **禁用系统代理**，
否则会被代理吞掉返回 HTML；成功码在 `state.code`，不是顶层 `code`。

---

## 输出结构

```
<下载目录>\<营名>\<序号>.<课名>.<YYYY.MM.DD>.mp4

例：Z:\太极营\道德经诵读\1.《道德经》一至三章.2026.07.27.mp4
```

- 序号 = 营内课表顺序（从 1 起，与 App 列表一致）
- 日期 = 该节课的 `startTime`；课名里的全角冒号 `：` 原样保留
- 不产生 `-1` / `-2` 重名后缀；同名旧文件按「整组」识别
- 音频课保留原始容器（`.mp3` / `.m4a`），不强行塞进 MP4

命名规则的唯一事实来源是 `xqd_api.course_filename()`。

---

## 代码结构

```
采集层   xqd.py（ADB/DOM） · _lel/api/qianliao.py（业务网关）
   ↓
业务层   xqd_app.py · xqd_api.py
   ↓
┌──────────────┬───────────────────┬────────────────────┐
│ xqd_gui.py   │ xqd_server.py     │ xqd_pdl.py         │
│ ★ 桌面工具   │ + ui.html 网页版  │ + xqd_batch.py     │
│              │                   │   CLI 全量批处理   │
└──────────────┴───────────────────┴────────────────────┘
   │
   ├─ xqd_platform.py  平台适配层（Platform 基类 + REGISTRY，新平台只写子类）
   ├─ xqd_engine.py    下载引擎（清单解析 / 并行分片 / 转封装 / 进度上报）
   ├─ xqd_auth.py      免 adbd 授权（读本机登录态）
   ├─ xqd_history.py   下载历史 + 分片缓存（跨会话续传）
   ├─ xqd_dedupe.py    已下载检测 / 残件清理
   └─ xqd_proc.py      无控制台窗口的子进程调用层（避免 Windows Terminal 闪窗）

build_exe.py           PyInstaller 打包
docs/                  设计与验证文档（见下）
state/                 运行期数据（部分已忽略，不入版本库）
archive/ · _lel/       一次性探测脚本与第三方分析材料（非运行时主链路）
```

> `archive/` 只保留**有复用价值**的材料：DRM 明文孪生的推导脚本
> （`archive/drm-analysis/`）、第三方提取脚本（`archive/xwz-v2/`）、
> 端到端验证脚本（`archive/oneshot/`）、早期网页版文档存档
> （`archive/legacy-docs/`）。抓包原件与明文凭据已清理。

**授权链路**：`xqd_auth.py` 通过 MuMu 模拟器自带的内部 RPC 读取本机登录态，
全程不启 adb、不依赖 adb 端口，也不会把任何凭据写进仓库或上传。
细节见 [`docs/11-工具实现要点.md`](docs/11-工具实现要点.md) A 节。

---

## 测试

离线回归集中在 `_lel/api/test_*.py`（280+ 项，明细见 GUI 工具说明）：

```bash
cd _lel/api
python test_states.py       # 三处状态一致 / 终态守卫
python test_history.py      # 下载历史与续传
python test_eta.py          # 速度与剩余时间估算
python test_dedupe.py       # 已下载检测与命名
```

★ **跑测试前必须设 `XQD_TEST_HOME`** 指向隔离目录，否则会改动真实的
配置、下载历史与分片缓存，甚至写到用户的下载目录。

`test_*_real.py` 是真网络端到端测试，需要有效的本机授权，并且同样必须隔离；
它们验证的是跨会话续传、三处状态一致等关键行为。

---

## 文档索引

**动手改代码前先读 `docs/01`，能省掉大量重复探测。**

| 文件 | 内容 |
|---|---|
| [`01-已验证事实.md`](docs/01-已验证事实.md) | ⭐ **权威结论清单**，所有已实测确认的事实 |
| [`03-踩坑与修复记录.md`](docs/03-踩坑与修复记录.md) | 实际浪费过时间的坑 |
| [`06-技术路线评估.md`](docs/06-技术路线评估.md) | 技术路线评估 |
| [`07-学无止V2.19.70分析.md`](docs/07-学无止V2.19.70分析.md) | 第三方客户端分析记录 |
| [`08-自建通用下载内核架构.md`](docs/08-自建通用下载内核架构.md) | 自建通用下载内核架构 |
| [`09-兴趣岛业务API.md`](docs/09-兴趣岛业务API.md) | 业务网关契约（端点 / 参数 / 成功码） |
| [`10-GUI工具说明.md`](docs/10-GUI工具说明.md) | 界面、状态、ETA、历史、打包、回归清单 |
| [`11-工具实现要点.md`](docs/11-工具实现要点.md) | 实现细节：授权 / MuMu / 速率 / 状态 / 续传 / 测试隔离 |
| [`12-项目现状与合规.md`](docs/12-项目现状与合规.md) | 代码结构、环境、合规声明、当前进度 |

> 早期网页版时代的架构 / 需求 / 待办三份文档已移至
> `archive/legacy-docs/`，仅作历史存档，**不代表当前状态**。

---

## 打包与分发

```bash
python build_exe.py              # 产出 dist/xingqudao-downloader-v1.5.1.exe
python build_exe.py --dry-run    # 只打印命令，不执行打包
```

★ **产物文件名固定为纯 ASCII**：`xingqudao-downloader-v<版本>.exe`，
版本号自动取自 `xqd_gui.APP_VERSION`，与 Release 的 tag 对齐。原因：GitHub
Releases 会把中文附件名吞成 `default.exe`，而附件发布后不可改名，只能从打包
源头避开。窗口标题、界面文字仍为中文（`APP_TITLE`），不受影响。

打包 PySide6 必须显式收集顶层 `Qt6*.dll` 与 `plugins/`，`build_exe.py` 已处理。

★ **exe 不纳入 git 仓库**，通过 GitHub Releases 附件分发。原因：
GitHub 单文件上限 100 MB，而该 exe 约 96.5 MB 已贴边；二进制无法增量存储，
每次重新打包都会让仓库永久增大约 96 MB；PyInstaller 内部已压缩过，
实测再套 deflate 只省 **0.6%**，压缩解决不了问题。

---

## 已知约束

- 改过 `xqd_app.py` / `xqd_api.py` 后必须重启本地服务。
- 转封装用**按序 cat 字节拼接**，不要用 ffmpeg concat demuxer
  （后者会重置时间戳，实测成品比清单长 6 秒）。
- 分片临时目录要**逐个删**：批量删除会触发安全删除阈值被拦，导致目录累积。
- 网络不稳定、流量昂贵：下载前先探测有效性，抽样片写盘复用，续传优先读本地缓存。
- 课程内容导出后请及时删除，不要长期留存。

---

## 合规与使用边界

- 本仓库**运行时主链路为独立编写**，不含任何账号体系、加密服务或商业客户端代码，
  也不含任何账号凭据（凭据值在入库前已全部替换为占位符）。
- `_lel/` 下的分析材料与 163 解密内核属于对第三方客户端的分析/独立复现记录，
  **不在其上游仓库的 MIT 授权范围内**，不得声称 MIT。完整声明见
  [`NOTICE.md`](NOTICE.md)。
- 课程内容的权利不因本软件改变。请**只处理自己已购买、有权访问与保存的内容**，
  本工具不提供、也不鼓励用于未购内容的批量获取；仅供个人学习与本地教学使用。

---

# 分支 `csharp-wpf`：C# + WPF 完整移植

> 本分支把 master 的 **全部功能**从 Python 移植为 C# / WPF，`master` 分支保持
> Python 实现不变。上面的 Python 版说明仍然有效；以下只描述 C# 分支。

## 环境与构建

| 项 | 值 |
|---|---|
| 目标框架 | `net8.0`（Core / Server / CLI / Tests）、`net8.0-windows` + `UseWPF`（GUI） |
| SDK | .NET 8 SDK 8.0.416（本机装在 `D:\user\chisenin\.dotnet`，**不改动系统目录**） |
| 运行时 | 系统自带 `Microsoft.NETCore.App` + `Microsoft.WindowsDesktop.App` 8.0.22 |
| 外部包 | **零 NuGet 依赖**，全部只用 BCL（System.Text.Json / HttpClient / Process / WPF） |
| 外部工具 | ffmpeg / ffprobe（与 Python 版相同，需在 PATH 或固定回退目录） |

```bash
DOTNET="D:/user/chisenin/.dotnet/dotnet.exe"

# 编译整个解决方案（5 个项目，0 错误 0 警告）
"$DOTNET" build src/Xqd.sln -c Release

# 离线回归（199 项，不发网络请求、不启动模拟器、XQD_TEST_HOME 隔离）
"$DOTNET" run --project src/Xqd.Tests -c Release

# 发布三个可执行程序到 dist-csharp/（framework-dependent，需系统 .NET 8）
"$DOTNET" publish src/Xqd.Gui/Xqd.Gui.csproj    -c Release -o dist-csharp/gui
"$DOTNET" publish src/Xqd.Server/Xqd.Server.csproj -c Release -o dist-csharp/server
"$DOTNET" publish src/Xqd.Cli/Xqd.Cli.csproj    -c Release -o dist-csharp/cli
```

日常使用：双击 `dist-csharp/gui/xingqudao-downloader.exe`（绿色免安装目录，
整目录一起拷贝即可；不要只拷单个 exe）。

```bash
# 网页版（复用根目录 ui.html，接口与 Python 版一致）
"$DOTNET" dist-csharp/server/Xqd.Server.dll --port 8765 --mode api --out "D:/user/chisenin/Videos"

# CLI 全量批处理
"$DOTNET" dist-csharp/cli/Xqd.Cli.dll --out "Z:/太极营" --workers 2 \
    --seg-workers 12 --tabs 正式营,体验营 --quality max
```

★ `PublishSingleFile=true` 在本机会触发 `Microsoft.NET.ILLink.Tasks` 的 NuGet 还原，
离线环境不可用，故采用普通目录发布（每个前端约 0.5 MB，共用系统 .NET 8 运行时）。

## 模块对照表

| Python（master） | C#（csharp-wpf） | 说明 |
|---|---|---|
| `xqd_platform.py` / `xqd_api.py` | `Xqd.Core/Api/{QianliaoClient,QianliaoPlatform,ApiCompat}.cs` | 网关 `transferData` / `state.code` / 禁代理 / 营表 / 播放地址 |
| `xqd_engine.py` | `Xqd.Core/Engine/*.cs` | 清单分派、DRM 明文孪生、12 片抽样、并发分片、cat 拼接、转封装、ffprobe |
| `xqd_auth.py` / `xqd_creds.py` / `xqd_proc.py` | `Xqd.Core/Auth/MumuAuth.cs` + 公共 `Creds.cs` / `Proc.cs` | MuMu 内部 RPC 读 Cookie、缓存授权优先、Qt 环境净化、无控制台窗口 |
| `xqd_history.py` / `xqd_dedupe.py` | `Xqd.Core/History/HistoryStore.cs` / `Dedupe/ExistingChecker.cs` | 跨会话续传分片、终态保护、已下载检测 |
| `xqd_gui.py`（3710 行） | `Xqd.Gui/*`（XAML + code-behind + 控件 + VM） | v1.5.1 全功能：多营勾选、6 列表格、双速率计、双槽位流水线、暂停/续传、日志 |
| `xqd_server.py` + `ui.html` | `Xqd.Server/*` + 复用的 `ui.html` | HttpListener 回环服务，路由/JSON 协议完全一致 |
| `xqd_batch.py` / `xqd_pdl.py` | `Xqd.Cli/*` | 全量批处理、断点状态、参数一致 |
| `xqd.py` / `xqd_app.py` | `Xqd.Core/Adb/*.cs` | ADB 采集、uiautomator DOM、sweep、明文孪生 |
| `_lel/core/netease_mooc.py` | `Xqd.Core/Crypto/Netease163.cs` | 163 AES 内核（**非 MIT**，见 NOTICE） |
| `build_exe.py` | `dotnet publish` | 不再需要 PyInstaller / Qt DLL 收集 |

## 移植时保持的关键契约

- **单一事实来源**：`Xqd.Core/States.cs`（状态词 / 配色 / 列号 / 槽位常量）、
  `Naming.cs`（`<序号>.<课名>.<YYYY.MM.DD>.mp4`）、`Config.cs`（目录记忆 / 注册表
  Known Folder GUID / 测试隔离）、`Contracts.cs`（所有前端共用的接口）。
- **少请求**：调用方现场解析的 `PlayUrl` 直接传给引擎，不重复 resolve；
  `api` 模式不 sweep；轻课直接返回空，不探测。
- **续传**：`%05d_<basename>` 分片命名、成功才清分片、`if (ownDir || (ok && !keepParts))`。
- **三处状态一致**：课名后状态词 / 下载管理状态列 / 运行日志共用 `States` 词表，
  终态守卫 + 阶段白名单含全部进行中阶段。
- 凭据仍只从 `XQD_COOKIE` / `QLD_COOKIE` / `%USERPROFILE%\.xqd_tool\cookie.txt` 读取，
  **代码里绝不硬编码**；`XQD_TEST_HOME` 只隔离配置/历史/分片，不影响凭据读取。

## 验证结果

- `dotnet build src/Xqd.sln -c Release`：**0 错误 / 0 警告**。
- 离线回归 **199 项全绿**（命名、状态、格式、配置隔离、历史合并、去重、
  引擎分片/孪生/短边、ADB DOM、API 契约、Qt 环境净化、服务装配）。
- 三个前端均已 Release 发布；WPF 实机启动确认窗口标题
  「兴趣岛视频下载器 v1.5.1」、进程响应正常、无未处理异常；
  本地服务 `/api/state`、`/`（`ui.html` 16.6 KB）、`/api/camps?tab=轻课`（空）已实跑通过。
- ⚠️ **未做真网络全量下载**（网络不稳定、流量昂贵，且 master 已端到端验证过 6/6）；
  下载链路的行为由离线断言 + 与 Python 版逐行对照保证。

