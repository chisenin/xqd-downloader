# 兴趣岛视频下载器

把「兴趣岛」App（`com.qlchat.xingqudao`）中**已购买课程**的视频批量导出为通用 MP4，
用于在本地教学大屏上播放。DRM 课程走同目录下的明文孪生清单，**无需解密**。

> 用途是临时转移到教学大屏，看完及时删除（大屏磁盘空间有限）。
> 本工具只处理自己有权访问与保存的内容，详见文末「合规与使用边界」。

## ★ v1.6.1 起：仓库只剩 C# / WPF 一套实现

| 项 | 内容 |
|---|---|
| 源码 | `src/Xqd.sln` —— 六个项目：`Xqd.Core` / `Xqd.Controls` / `Xqd.Gui` / `Xqd.Server` / `Xqd.Cli` / `Xqd.Tests` |
| 界面 / 运行时 | WPF / .NET 8 |
| Release 产物 | `xqd-downloader-vX.Y.Z.zip`（目录发布，约 250 KB，需系统 .NET 8 桌面运行时） |

**v1.6.1 起，Python 实现已从仓库删除**（原先的 `csharp-wpf` 分支与
`v1.5.2` / `v1.5.2-csharp-wpf` 两个 Release 仍作历史保留）。
`_lel/` 只保留**合规与分析材料**：`core/netease_mooc.py` 是 NOTICE 声明的对象，
`api/qianliao.py` 是业务网关的对照原稿 —— 运行时主链路全部是 C#。

**打包与编译都在 GitHub Actions 上完成，本机不产出二进制，仓库里也不放 exe / zip。**
推送 tag `vX.Y.Z` 会自动生成**一个** Release 和**一个**附件（版本号与 tag 一致）：

```
xqd-downloader-vX.Y.Z.zip   ← gui/xqd-downloader-vX.Y.Z.exe + cli/ + README.txt
```

`server/`（本地网页版）不再随包发布，需要时从源码运行。详见下文「GitHub Actions 发版」。

---

## 能做什么

- 拉取**全部营列表**（含公开课）与课表。课名一次拿全，不靠播放反推。
  公开课（没有 campId、靠 periodId 取课表的那批）同样能下载。
- 并行分片下载 → 转封装 MP4 → ffprobe 校验时长；实测 16~32 并发约 8.4 MB/s，
  瓶颈在 CDN 而非本地磁盘。
- 自动跳过已下载的课，残缺文件清理后用规范名覆盖重下。
- 暂停 / 继续、跨会话断点续传、下载历史恢复、下载目录记忆。
- 桌面 GUI：**单表 8 列**（状态胶囊 / 课程 / 所属营 / 时长 / 大小 / 速度 / 剩余 / 进度），
  多营合并、行选中只下其中几节、视图切换（全部 / 待下载 / 下载中 / 已完成 / 失败）、
  右键菜单删除成品；重新载入仍显示真实进度；进入封装阶段即释放网络槽位并行下一节；
  平时启动**直接用已保存的授权、不用开模拟器**，点「重新授权」才刷新。
- DRM 课自动选择同目录的明文孪生，并**按时长校验**，避免下错内容。
- 两种数据源：`api`（默认，**下载过程不需要模拟器**）/ `adb`（旧路径，需 MuMu 桥接）。
- 三种前端：桌面 GUI（主）、本地网页版（`src/Xqd.Server/ui.html`）、CLI 全量批处理。

---

## 快速开始

### 方式一：下载发行包（推荐）

到 [GitHub Releases](https://github.com/chisenin/xqd-downloader/releases) 取最新版：

```
xqd-downloader-vX.Y.Z.zip      解压后整目录拷贝，双击 gui/xqd-downloader-vX.Y.Z.exe
```

> 不要只拷单个 exe：同级目录里的 `Xqd.Core.dll`、`*.runtimeconfig.json` 等是必需的。

#### 先装 .NET 8 桌面运行时（约 55 MB，装一次就够）

本工具是 WPF 程序，**不把 .NET 运行时打包进 zip**（那样压缩包会涨到 160 MB）。
首次使用请先装一次运行时：

| 用途 | 链接 |
|---|---|
| 官方下载页（中文） | https://dotnet.microsoft.com/zh-cn/download/dotnet/8.0 |
| 官方下载页 | https://dotnet.microsoft.com/download/dotnet/8.0 |
| 官方直链（win-x64，8.0.22） | https://builds.dotnet.microsoft.com/dotnet/WindowsDesktop/8.0.22/windowsdesktop-runtime-8.0.22-win-x64.exe |

> **装不上或不确定？直接双击 `gui/启动.bat`** —— 它是纯 cmd 写的（不依赖 .NET 就能跑），
> 会检测运行环境：缺运行时就把下载链接摆出来并引导安装，装好后自动启动工具。

#### ffmpeg / ffprobe 不用手动装

分片转封装与成品时长校验需要 ffmpeg / ffprobe。**首次启动时工具会自动检测**，
缺失就弹「运行环境检查」窗口，点「立即下载安装」即可：

- **下载源优先走非 GitHub 的国内 CDN**（阿里 npmmirror，实测 ~200 KB/s），
  失败才退到 ffmpeg 官方构建站，最后才用带代理的 GitHub 源（ghfast.top / gh-proxy.com）。
- 装到 `%USERPROFILE%\.xqd_tool\ffmpeg\bin` —— **不写系统 PATH、不需要管理员权限**。
- 已经装在 PATH 或引擎回退目录里的 ffmpeg 会被直接识别，不会重复下载。

顶栏也有「环境检查」按钮，随时可以手动再查一次。

批量部署 / CI 场景可以走命令行模式（无界面，退出码 0 = 成功）：

```bash
gui/xqd-downloader-vX.Y.Z.exe --install-deps
```

已装好时直接返回「依赖已齐全」，不会重复下载。

操作流程：授权状态就绪 → 左栏按**真实营名**列出全部营
（分「已购课程 / 公开课」两组，顶部可搜索营名；标题栏可全选）→
**勾选一个或多个营** → 表格里**选中要下的几行**
（不选 = 下当前视图全部待下载；双击某行 = 只下这一节）→ 点「下载」。
「速度 / 剩余 / 进度」列显示实时值；成品文件名里的序号与日期照旧保留
（界面不再显示这两列）。点顶栏标题区可打开「使用说明与关于」。

版本号以 `src/Xqd.Core/States.cs` 的 `States.AppVersion` 为准；
界面细节见 [`docs/10-GUI工具说明.md`](docs/10-GUI工具说明.md)，
C# 版专门说明见 [`README-csharp-wpf.md`](README-csharp-wpf.md)。

### 方式二：本地网页版

```bash
dotnet publish src/Xqd.Server/Xqd.Server.csproj -c Release -o dist-csharp/server
dotnet server/Xqd.Server.dll --port 8765 --mode api --out "D:/user/chisenin/Videos"
```

浏览器打开 `http://127.0.0.1:8765/`。`--mode` 可取 `api`（默认）或 `adb`。
服务请用后台任务方式启动，用 `&` 会随 shell 退出被杀；改过业务层后**必须重启服务**。

### 方式三：CLI 全量批处理

```bash
dotnet cli/Xqd.Cli.dll --out "Z:/太极营" --workers 2 --seg-workers 12 \
                    --tabs 正式营,体验营 --quality max
```

可选参数：`--only`（只跑指定营/课）、`--quality max|720|1080`、
`--workers`（课程级并发）、`--seg-workers`（分片并发）。

---

## 依赖

| 组件 | 用途 | 备注 |
|---|---|---|
| .NET 8 SDK / 桌面运行时 | 编译 / 运行 | **零第三方 NuGet 依赖**，只用 BCL + WPF；SDK 版本由根目录 `global.json` 锁定 8.0.x。发行包**不含**运行时，需自行安装（见「快速开始」） |
| ffmpeg / ffprobe | 分片转封装、成品时长校验 | **不必手动安装** —— 工具首次启动自动检测并提供一键下载安装（国内镜像优先） |
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
- 音频课保留原始容器（`.mp3` / `.m4a`），不强行塞进 MP4
- 命名规则的唯一事实来源是 `Xqd.Core/Naming.cs`。

---

## 代码结构

```
C#（src/，解决方案 Xqd.sln，6 个项目）
   Xqd.Core    公共契约：Models / States / Naming / Config / Creds / Proc /
               Net / Util / Api / Adb / Auth / Engine / History / Dedupe / Crypto
   Xqd.Controls  WPF 类库：MarqueeControl / StateColorConverter
               （XAML 引用的自定义控件，独立程序集以便干净构建时解析）
   Xqd.Gui     WPF 桌面工具（XAML + code-behind + 控件 + ViewModel）
   Xqd.Server  本地网页版（自带 ui.html，路由 / JSON 协议一致）
   Xqd.Cli     CLI 全量批处理
   Xqd.Tests   离线回归（直接链接编译 GUI 的 ViewModel 源码）

_lel/                         ★ 只保留合规与分析材料（运行时不用）
   core/netease_mooc.py        163 解密内核原稿（NOTICE 声明的对象）
   api/qianliao.py             业务网关对照原稿
   login/ v2/                  客户端逆向过程记录

.github/workflows/release.yml   发版工作流
docs/                          设计与验证文档
```

> `_lel/` 是一次性探测脚本与第三方分析材料，不是运行时主链路；
> 抓包原件与明文凭据已清理。Python 实现与 `archive/` 已于 v1.6.1 删除。

**授权链路**：通过 MuMu 模拟器自带的内部 RPC 读取本机登录态，全程不启 adb、
不依赖 adb 端口，也不会把任何凭据写进仓库或上传。
详见 [`docs/11-工具实现要点.md`](docs/11-工具实现要点.md) A 节。

### 与早期 Python 实现的模块对照

> Python 实现已于 v1.6.1 删除；下表留作**移植对照**，便于理解各模块的来源。

| Python（已删） | C# | 说明 |
|---|---|---|
| `xqd_platform.py` / `xqd_api.py` | `Xqd.Core/Api/{QianliaoClient,QianliaoPlatform,ApiCompat}.cs` | 网关 `transferData` / `state.code` / 禁代理 / 营表 / 播放地址 |
| `xqd_engine.py` | `Xqd.Core/Engine/*.cs` | 清单分派、DRM 明文孪生、12 片抽样、并发分片、cat 拼接、转封装、ffprobe |
| `xqd_auth.py` / `xqd_creds.py` / `xqd_proc.py` | `Xqd.Core/Auth/MumuAuth.cs` + `Creds.cs` / `Proc.cs` | MuMu 内部 RPC 读 Cookie、缓存授权优先、Qt 环境净化、无控制台窗口 |
| `xqd_history.py` / `xqd_dedupe.py` | `Xqd.Core/History/HistoryStore.cs` / `Dedupe/ExistingChecker.cs` | 跨会话续传分片、终态保护、已下载检测 |
| `xqd_gui.py` | `Xqd.Gui/*` | 单表 8 列、行选中、状态胶囊、视图切换、双速率计、双槽位流水线、暂停/续传、日志 |
| `xqd_server.py` + `ui.html` | `Xqd.Server/*` + 同一个 `ui.html` | 回环服务，路由/JSON 协议完全一致 |
| `xqd_batch.py` / `xqd_pdl.py` | `Xqd.Cli/*` | 全量批处理、断点状态、参数一致 |
| `xqd.py` / `xqd_app.py` | `Xqd.Core/Adb/*.cs` | ADB 采集、uiautomator DOM、sweep、明文孪生 |
| `_lel/core/netease_mooc.py` | `Xqd.Core/Crypto/Netease163.cs` | 163 AES 内核（**非 MIT**，见 NOTICE） |
| `build_exe.py` | `dotnet publish` | 分别产出 exe / zip |

两套实现保持同一套关键契约：状态词 / 列号 / 命名 / 配置隔离的单一事实来源，
`api` 模式不 sweep、轻课直接返回空，`%05d_<basename>` 分片命名与成功才清缓存的续传规则，
凭据只从 `XQD_COOKIE` / `%USERPROFILE%\.xqd_tool\cookie.txt` 读取，**代码里绝不硬编码**。

---

## GitHub Actions 发版

工作流文件：[`.github/workflows/release.yml`](.github/workflows/release.yml)。
**打包与编译只在 GitHub 的 Windows runner 上执行**，本机不需要装 .NET SDK。

| 触发 | 行为 |
|---|---|
| 推送 tag `vX.Y.Z` | 解析版本号 → 构建 C# 产物 → 创建一个 Release 并挂**一个**附件 |
| 手动 `workflow_dispatch` | 填版本号重跑；Release 已存在时**直接报错**（见下） |

三个作业：

1. `prepare`：从 tag（或手动输入）取版本号，校验 `X.Y.Z` 格式。
2. `build-csharp`（`windows-2022`）：.NET 8 SDK，校验 `States.AppVersion` 与 tag 一致，
   `dotnet build` 全解决方案 + 离线回归 `Xqd.Tests`，再 `dotnet publish` 两个前端到
   `gui/ cli/`（GUI 用 `-p:PkgVersion` 让 exe 带版本号），
   去掉 `.pdb`、附 `README.txt` 后压缩成 `xqd-downloader-vX.Y.Z.zip`。
3. `release`：自动生成含 SHA-256 的发行说明，用
   `GITHUB_TOKEN`（`permissions: contents: write`）创建 Release。
   若同名 Release 已存在则**明确报错并停止**，绝不自动删除已发布 Release。

> ★ 几个**只在干净 CI 环境出现**的坑（本机不会复现）：
> - Windows runner 控制台默认是 cp1252，`build_exe.py` 打印中文会抛
>   `UnicodeEncodeError` → 工作流设 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`。
> - 干净构建时 XAML 引用**同程序集**自定义控件会报 MC3074（`clr-namespace` 补
>   `;assembly=` 也救不回来，本机因 `obj/` 有增量缓存而被掩盖）。最终把
>   `MarqueeControl` / `StateColorConverter` 拆到 `Xqd.Controls` 类库，XAML 改为
>   `;assembly=Xqd.Controls`，从**已编译的引用程序集**解析，彻底绕开 markup compile 的本地类型解析。
>   根目录 `global.json` 另把 .NET SDK 锁在 8.0.x，避免 runner 上更高版本 SDK 改变编译行为。
> - C# 离线回归依赖**本机时区**（`startTime` 按本地时间格式化）与 ffmpeg/ffprobe
>   的 PATH 查找。CI 里把 runner 时区设为 `China Standard Time`，并放两个占位
>   `ffmpeg.exe` / `ffprobe.exe`（回归只验证查找逻辑，不执行外部工具）。
> - （历史）Python 依赖**只能装 `PySide6-Essentials`**：完整 `PySide6` 元包会带上
>   QtWebEngine 等 Addons，PyInstaller 会把它们全收进 exe，实测从约 96 MB 膨胀到
>   330 MB。Python 版已于 v1.6.1 删除，该坑不再适用。
> - GitHub 的 **immutable release** 发布后不能覆盖/删除单个附件（`--clobber` 报
>   HTTP 422 `Cannot delete asset from an immutable release`）；删掉整个 Release
>   后也**不能复用同一 tag**（`tag_name was used by an immutable release`）。
>   → 一个版本号只能发一次，发现产物有问题必须**换版本号重发**；
>   工作流遇到已存在 Release 会直接报错，避免误删已发布版本。
>
> ⚠️ **当前状态（2026-11-08）：v1.5.4 待发布（无边框窗口 + 自绘窗口按钮）。**
> v1.5.3 的 tag 已被一次不可变 Release 占用，无法再用该名字发版，故跳到 v1.5.4。

发版操作（maintainer）：

```bash
# 1. 改版本号（C# 版唯一来源 + 回归断言，两处必须一致）
#    src/Xqd.Core/States.cs : States.AppVersion   ← 唯一来源，CI 会校验与 tag 一致
#    src/Xqd.Tests/Program.cs : 版本断言
#    （版本号只有这两处；Python 版已于 v1.6.1 删除）
git add -A && git commit -m "release: vX.Y.Z"
git push origin master

# 2. 打 tag 触发工作流
git tag vX.Y.Z && git push origin vX.Y.Z
```

> ★ 产物名固定为纯 ASCII —— GitHub Releases 会把中文附件名吞成 `default.exe`，
> 而大附件发布后不可改名。窗口标题、界面文字仍是中文。
> ★ 二进制不进仓库，只走 Release 附件：git 对二进制无法增量存储，
> 每次重新打包都会让仓库永久膨胀，而 Release 附件的容量上限远高于仓库内单文件。

本地开发时如需自行验证（**非正式发版通道**）：

```bash
dotnet build src/Xqd.sln -c Release
dotnet publish src/Xqd.Gui/Xqd.Gui.csproj -c Release -o dist-csharp/gui -p:PkgVersion=1.5.4
```

★ exe 名带版本号靠 `-p:PkgVersion=X.Y.Z` 传给 `Xqd.Gui.csproj`
（它派生出 `AssemblyName=xqd-downloader-v$(PkgVersion)`）。
**不要用 `-p:AssemblyName=`** —— 那是 MSBuild 全局属性，会被 NuGet restore
当成项目名，报 `Ambiguous project name` 直接失败。

★ C# 版采用 **framework-dependent 目录发布**：每个前端约 0.5 MB，共用系统 .NET 8 运行时。
发行包**刻意不打包运行时**（自包含单文件 162 MB、目录发布 162 MB，太大），
改为在 README / Release 说明页给下载链接，并在 `gui/启动.bat` 里做检测与引导。

★ `NuGet.config` 显式声明 nuget.org：本机默认 NuGet 源会被系统代理吞掉，
还原 runtime pack 时直接 NU1100 失败；显式声明后恢复正常（2026-11-08 实测）。

---

## 测试

```bash
# C# 离线回归（280 项，不发网络请求、不启动模拟器）
dotnet run --project src/Xqd.Tests -c Release
```

★ 测试自己会设 `XQD_TEST_HOME` 指向隔离目录，不会改动真实的配置、
下载历史与分片缓存。

---

## 文档索引

**动手改代码前先读 `docs/01`，能省掉大量重复探测。**

| 文件 | 内容 |
|---|---|
| [`01-已验证事实.md`](docs/01-已验证事实.md) | ⭐ **权威结论清单**，所有已实测确认的事实 |
| [`03-踩坑与修复记录.md`](docs/03-踩坑与修复记录.md) | 实际浪费过时间的坑 |
| [`06-技术路线评估.md`](docs/06-技术路线评估.md) | 技术路线评估 |
| [`09-兴趣岛业务API.md`](docs/09-兴趣岛业务API.md) | 业务网关契约（端点 / 参数 / 成功码） |
| [`10-GUI工具说明.md`](docs/10-GUI工具说明.md) | 界面、状态、ETA、历史、打包、回归清单 |
| [`11-工具实现要点.md`](docs/11-工具实现要点.md) | 授权 / MuMu / 速率 / 状态 / 续传 / 测试隔离 |
| [`12-项目现状与合规.md`](docs/12-项目现状与合规.md) | 代码结构、环境、合规声明、当前进度 |
| [`RELEASE_NOTES.md`](RELEASE_NOTES.md) | 当前版本发行说明与历史校验信息 |
| [`README-csharp-wpf.md`](README-csharp-wpf.md) | C# / WPF 实现的专门说明 |

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
  [`NOTICE.md`](NOTICE.md)（含 C# 实现的组件与授权边界）。
- 课程内容的权利不因本软件改变。请**只处理自己已购买、有权访问与保存的内容**，
  本工具不提供、也不鼓励用于未购内容的批量获取；仅供个人学习与本地教学使用。
