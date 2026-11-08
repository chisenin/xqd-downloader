# 兴趣岛视频下载器

把「兴趣岛」App（`com.qlchat.xingqudao`）中**已购买课程**的视频批量导出为通用 MP4，
用于在本地教学大屏上播放。DRM 课程走同目录下的明文孪生清单，**无需解密**。

> 用途是临时转移到教学大屏，看完及时删除（大屏磁盘空间有限）。
> 本工具只处理自己有权访问与保存的内容，详见文末「合规与使用边界」。

## ★ v1.5.3：一个分支，两套实现，一个 Release

`master` 同时保留两套功能对齐的实现，源码都在这个仓库里：

| 实现 | 源码 | 界面 / 运行时 | 产物 |
|---|---|---|---|
| Python | 根目录 `xqd_*.py` · `_lel/api/qianliao.py` | PySide6（Qt6） | PyInstaller 单文件 exe，约 96 MB |
| C# | `src/Xqd.*` 五个项目 | WPF / .NET 8 | 目录发布 zip，约 250 KB，需系统 .NET 8 桌面运行时 |

原先的 `master`（Python）与 `csharp-wpf`（C#）两个分支已合并到 `master`；
旧分支与 `v1.5.2` / `v1.5.2-csharp-wpf` 两个 Release 保留作历史，不再更新。

**从 v1.5.3 起，打包与编译都在 GitHub Actions 上完成，本机不产出二进制，
仓库里也不放 exe / zip。** 推送 tag `vX.Y.Z` 会自动生成**一个** Release，
同时挂两个附件（版本号与 tag 一致）：

```
xingqudao-downloader-vX.Y.Z.exe   ← Python / PySide6，双击即用
xingqudao-downloader-vX.Y.Z.zip   ← C# / WPF，解压后整目录拷贝
```

按需二选一即可，不必同时安装。详见下文「GitHub Actions 发版」。

---

## 能做什么

- 拉取**正式营 / 体验营**的营列表与课表。课名一次拿全，不靠播放反推。
- 并行分片下载 → 转封装 MP4 → ffprobe 校验时长；实测 16~32 并发约 8.4 MB/s，
  瓶颈在 CDN 而非本地磁盘。
- 自动跳过已下载的课，残缺文件清理后用规范名覆盖重下。
- 暂停 / 继续、跨会话断点续传、下载历史恢复、下载目录记忆。
- 桌面 GUI：多营勾选合并、标题前缀保留原营序号、重新载入仍显示真实进度、
  进入封装阶段即释放网络槽位并行下一节；平时启动**直接用已保存的授权、
  不用开模拟器**，点「重新授权」才刷新（子进程 Qt 环境已隔离）。
- DRM 课自动选择同目录的明文孪生，并**按时长校验**，避免下错内容。
- 两种数据源：`api`（默认，**下载过程不需要模拟器**）/ `adb`（旧路径，需 MuMu 桥接）。
- 三种前端各有两套实现：桌面 GUI、本地网页版（`ui.html` 共用）、CLI 全量批处理。

---

## 快速开始

### 方式一：下载发行包（推荐）

到 [GitHub Releases](https://github.com/chisenin/xqd-downloader/releases) 取最新版：

```
xingqudao-downloader-v1.5.3.exe      双击即用，绿色免安装
xingqudao-downloader-v1.5.3.zip      解压后整目录拷贝，双击 gui/xingqudao-downloader.exe
```

> C# 版不要只拷单个 exe：同级目录里的 `Xqd.Core.dll`、`*.runtimeconfig.json` 等是必需的。
> 两个版本都需要 ffmpeg / ffprobe 在 PATH（或引擎的查找路径）。

源码运行（Python 版）：

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

Python 版版本以 `xqd_gui.py` 的 `APP_VERSION` 为准，C# 版以
`src/Xqd.Core/States.cs` 的 `States.AppVersion` 为准；界面细节见
[`docs/10-GUI工具说明.md`](docs/10-GUI工具说明.md)，C# 版专门说明见
[`README-csharp-wpf.md`](README-csharp-wpf.md)。

### 方式二：本地网页版

```bash
# Python
python -u xqd_server.py --mode api --port 8765 --out "D:/user/chisenin/Videos"

# C#（目录发布后）
dotnet server/Xqd.Server.dll --port 8765 --mode api --out "D:/user/chisenin/Videos"
```

浏览器打开 `http://127.0.0.1:8765/`。`--mode` 可取 `api`（默认）或 `adb`。
服务请用后台任务方式启动，用 `&` 会随 shell 退出被杀；改过业务层后**必须重启服务**。

### 方式三：CLI 全量批处理

```bash
python xqd_batch.py --out "Z:/太极营" --workers 2 --seg-workers 12 \
                    --tabs 正式营,体验营 --quality max

dotnet cli/Xqd.Cli.dll --out "Z:/太极营" --workers 2 --seg-workers 12 \
                    --tabs 正式营,体验营 --quality max
```

可选参数：`--only`（只跑指定营/课）、`--quality max|720|1080`、
`--workers`（课程级并发）、`--seg-workers`（分片并发）。

---

## 依赖

| 组件 | 用途 | 备注 |
|---|---|---|
| Python 3.8+ | Python 版运行时 | 业务 HTTP / 服务 / 下载内核**只用标准库** |
| PySide6-Essentials | Python 版 GUI / 打包 | 仅 GUI 与 PyInstaller 打包需要 |
| .NET 8 SDK / 桌面运行时 | C# 版编译 / 运行 | **零第三方 NuGet 依赖**，只用 BCL + WPF |
| ffmpeg / ffprobe | 分片转封装、成品时长校验 | 两个版本共用，需在 PATH 或引擎回退目录 |
| pycryptodome | 163 地址解密内核 | 仅 `_lel/core/netease_mooc.py`，兴趣岛主链路不需要 |
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
- Python 版命名规则的唯一事实来源是 `xqd_api.course_filename()`；
  C# 版是 `Xqd.Core/Naming.cs`，两者契约一致。

---

## 代码结构

```
Python（根目录）
采集层   xqd.py（ADB/DOM） · _lel/api/qianliao.py（业务网关）
   ↓
业务层   xqd_app.py · xqd_api.py · xqd_platform.py（平台适配 REGISTRY）
   ↓
┌──────────────┬───────────────────┬────────────────────┐
│ xqd_gui.py   │ xqd_server.py     │ xqd_pdl.py         │
│ ★ 桌面工具   │ + ui.html 网页版  │ + xqd_batch.py     │
│              │                   │   CLI 全量批处理   │
└──────────────┴───────────────────┴────────────────────┘
   ├─ xqd_engine.py    下载引擎（清单解析 / 并行分片 / 转封装 / 进度上报）
   ├─ xqd_auth.py      免 adbd 授权（读本机登录态）
   ├─ xqd_history.py   下载历史 + 分片缓存（跨会话续传）
   ├─ xqd_dedupe.py    已下载检测 / 残件清理
   └─ xqd_proc.py      无控制台窗口的子进程调用层（避免 Windows Terminal 闪窗）

C#（src/，解决方案 Xqd.sln，5 个项目）
   Xqd.Core    公共契约：Models / States / Naming / Config / Creds / Proc /
               Net / Util / Api / Adb / Auth / Engine / History / Dedupe / Crypto
   Xqd.Gui     WPF 桌面工具（XAML + code-behind + 控件 + ViewModel）
   Xqd.Server  本地网页版（复用根目录 ui.html，路由 / JSON 协议一致）
   Xqd.Cli     CLI 全量批处理
   Xqd.Tests   离线回归（直接链接编译 GUI 的 ViewModel 源码）

.github/workflows/release.yml   发版工作流
build_exe.py                   PyInstaller 打包脚本（供 CI 与本地开发使用）
docs/                          设计与验证文档
```

> `archive/` 与 `_lel/` 是一次性探测脚本与第三方分析材料，不是运行时主链路；
> 抓包原件与明文凭据已清理。

**授权链路**：通过 MuMu 模拟器自带的内部 RPC 读取本机登录态，全程不启 adb、
不依赖 adb 端口，也不会把任何凭据写进仓库或上传。
详见 [`docs/11-工具实现要点.md`](docs/11-工具实现要点.md) A 节。

### 两套实现的模块对照

| Python | C# | 说明 |
|---|---|---|
| `xqd_platform.py` / `xqd_api.py` | `Xqd.Core/Api/{QianliaoClient,QianliaoPlatform,ApiCompat}.cs` | 网关 `transferData` / `state.code` / 禁代理 / 营表 / 播放地址 |
| `xqd_engine.py` | `Xqd.Core/Engine/*.cs` | 清单分派、DRM 明文孪生、12 片抽样、并发分片、cat 拼接、转封装、ffprobe |
| `xqd_auth.py` / `xqd_creds.py` / `xqd_proc.py` | `Xqd.Core/Auth/MumuAuth.cs` + `Creds.cs` / `Proc.cs` | MuMu 内部 RPC 读 Cookie、缓存授权优先、Qt 环境净化、无控制台窗口 |
| `xqd_history.py` / `xqd_dedupe.py` | `Xqd.Core/History/HistoryStore.cs` / `Dedupe/ExistingChecker.cs` | 跨会话续传分片、终态保护、已下载检测 |
| `xqd_gui.py` | `Xqd.Gui/*` | 多营勾选、6 列表格、双速率计、双槽位流水线、暂停/续传、日志 |
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
**打包与编译只在 GitHub 的 Windows runner 上执行**，本机不需要装 PyInstaller / .NET SDK。

| 触发 | 行为 |
|---|---|
| 推送 tag `vX.Y.Z` | 解析版本号 → 并行构建两份产物 → 创建一个 Release 并挂两个附件 |
| 手动 `workflow_dispatch` | 填版本号重跑；Release 已存在时覆盖附件并更新说明 |

四个作业：

1. `prepare`：从 tag（或手动输入）取版本号，校验 `X.Y.Z` 格式。
2. `build-python`（`windows-2022`）：Python 3.13 + `PySide6==6.12.0` +
   `pyinstaller==6.22.3`，校验 `APP_VERSION` 与 tag 一致，跑 `build_exe.py`，
   产出 `xingqudao-downloader-vX.Y.Z.exe`。
3. `build-csharp`（`windows-2022`）：.NET 8 SDK，`dotnet build` 全解决方案 +
   离线回归 `Xqd.Tests`，再 `dotnet publish` 三个前端到 `gui/ server/ cli/`，
   去掉 `.pdb` 后压缩成 `xingqudao-downloader-vX.Y.Z.zip`。
4. `release`：汇总两个附件，自动生成含 SHA-256 的发行说明，用
   `GITHUB_TOKEN`（`permissions: contents: write`）创建 / 更新 Release。

发版操作（ maintainer ）：

```bash
# 1. 改版本号（两处必须一致）
#    xqd_gui.py: APP_VERSION
#    src/Xqd.Core/States.cs: States.AppVersion
#    以及两处离线回归的版本断言（_lel/api/test_mumu_env.py、src/Xqd.Tests/Program.cs）
git add -A && git commit -m "release: vX.Y.Z"
git push origin master

# 2. 打 tag 触发工作流
git tag vX.Y.Z && git push origin vX.Y.Z
```

> ★ 产物名固定为纯 ASCII —— GitHub Releases 会把中文附件名吞成 `default.exe`，
> 而大附件发布后不可改名。窗口标题、界面文字仍是中文。
> ★ exe 约 96.5 MB 已贴近 GitHub 单文件 100 MB 上限；PyInstaller 内部已压缩过，
> 实测再套 deflate 只省 0.6%，所以二进制不进仓库、只走 Release 附件。

本地开发时如需自行验证（**非正式发版通道**）：

```bash
python build_exe.py --dry-run          # 只打印 PyInstaller 命令
python build_exe.py                    # 产出 dist/xingqudao-downloader-v1.5.3.exe
dotnet build src/Xqd.sln -c Release
dotnet publish src/Xqd.Gui/Xqd.Gui.csproj -c Release -o dist-csharp/gui
```

★ `PublishSingleFile=true` 需要联网还原 `Microsoft.NET.ILLink.Tasks`，
故 C# 版采用 **framework-dependent 目录发布**：每个前端约 0.5 MB，共用系统 .NET 8 运行时。

---

## 测试

```bash
# Python 离线回归（集中在 _lel/api/test_*.py）
cd _lel/api && python test_states.py && python test_history.py

# C# 离线回归（224 项，不发网络请求、不启动模拟器）
dotnet run --project src/Xqd.Tests -c Release
```

★ **跑 Python 测试前必须设 `XQD_TEST_HOME`** 指向隔离目录，否则会改动真实的配置、
下载历史与分片缓存，甚至写到用户的下载目录。C# 测试自己会设这个变量。
`test_*_real.py` 是真网络端到端测试，需要有效的本机授权，同样必须隔离。

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
