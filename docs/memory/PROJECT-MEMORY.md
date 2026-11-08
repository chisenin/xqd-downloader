- ✅ **GUI v4（2026-11-07，本轮）**：下载管理表的**实时 ETA 估算**。
  - 表头从 5 列变 6 列：`['', 课程, 状态, 大小, 速度, 剩余时间]`。
    原来的「时间」列只是 `time.strftime` 墙上时钟，不是估算。
  - **速度** = 实测速率（最近 8 秒滑动窗口，非全程平均）。
  - **剩余时间** = 剩余量 ÷ 实时速率 → 随速度/剩余内容实时变化。
    进度用**时长占比**（每片时长精确，总字节数是外推估算）。
  - 状态列细分：解析中/下载中/封装中/校验中；完成后显示「用时 xx:xx」。
  - 标题旁全局汇总：`剩余约 12:30 · 3 个在跑 / 20 个排队`。
  - 暂停时冻结倒计时；封装阶段按 Z 盘写速单独估算。
  - 引擎：`on_progress` 扩为 4 参 + 新增 `on_phase` 回调；
    `_dl_all` 采样前 3 片写盘复用（省 3 次请求）。
  - 测试：test_eta 44 项 + test_eta_real 10 项（真实下载端到端）全通过。
- ✅ **GUI v5（2026-11-07，本轮）**：时间格式 + 「帮助」菜单。
  - **剩余时长改「天:时:分:秒」**，按需省略前导零单位：
    45 秒→`45` / 90 秒→`1:30` / 3661 秒→`1:01:01` / 93784 秒→`1:02:03:04`。
    最高位段不补零、其余两位。改的是 `fmt_dur()`，
    `_fmt_dur()`（课程时长列）**没改**。
  - **顶部「帮助」菜单**（QMenuBar，与蓝色顶栏同色连成一条带）：
    使用说明…(F1) / 关于本工具… / 退出(Ctrl+Q)。
    实现 = `_build_menus()` + `HtmlDialog`(QTextBrowser 显示 HTML)。
    ★ QMenu 是独立顶层窗口，父窗口 QSS 管不到 → 要单独 setStyleSheet。
  - ★ **本项目确实用了学无止下载器的部分材料**（只在 `_lel/` 下，
    运行时主链路完全自建）：
    `netease_mooc.py`(独立复现其 163 解密) / `_lel/login/`(app.asar 明文 JS)
    / `_lel/v2/`(PYZ 破解脚本) / `archive/xwz-v2/`(提取脚本)。
  - ★ **官方仓库 = `github.com/Xue-Wu-Zhi/xuewuzhi-downloader`**（MIT、24★）。
    它的 NOTICE 明确：**官方客户端不在 MIT 授权范围内**（核心引擎不在仓库里）
    → 我们复现的 163 内核不能声称 MIT。
    旧地址 `github.com/PyJun/Mooc_Downloader`（中文教程常引）**已 404**，
    不要引用。
  - 「关于」对话框 + 仓库根 `NOTICE.md` 都列了
    学无止(MIT)/PySide6(LGPL-3.0)/FFmpeg(LGPL|GPL)/pycryptodome(BSD-2|Public Domain)。
  - 测试：test_about 28 项(新建) + test_eta 49 项 全通过。
  - 版本 1.1.0，exe 已重新打包到桌面。
- ✅ **GUI v6（2026-11-07，本轮）**：撤掉「帮助」菜单栏 → 点标题区弹合并框。
  - 用户嫌「帮助」两个字占空间 → **整条 QMenuBar 撤掉**，顶栏直接贴上缘。
  - 新增 `BrandBox`（主标题+副标题包成一个控件）+ `ClickOverlay`（透明点击层）：
    ★ 必须 `setAutoFillBackground(False)` 否则盖成白块；★ 要 `raise_()`；
    ★ `resizeEvent` 里 `overlay.setGeometry(self.rect())` 铺满整个品牌区。
    视觉上完全透明、无按钮无链接，只用手型光标 + tooltip 提示可点。
  - **一个对话框**：`HELP_ABOUT_HTML = HELP_HTML + '<hr>' + ABOUT_HTML`
    → 上半是六步用法，往下拉是关于与开源声明。
  - 快捷键：**按要求不加 F1**；保留 Ctrl+Q（用 `self.addAction`，不挂菜单）。
  - 要彻底去掉菜单栏高度 → **根本不调用 `self.menuBar()`**。
  - 测试：test_about 重写 34 项（QTest.mouseClick 真实点击能弹窗）+ 全回归全绿。
  - 版本 1.2.0，exe 已重新打包到桌面。
- ✅ **后台批量下载已按用户要求停止**，后续统一用 GUI 工具下载。
- ⬜ 全量下载：9 个正式营共 266 节 + 体验营 6 节（用 GUI 工具跑）。
- ⬜ 163 适配器：解密内核已就绪（`_lel/core/netease_mooc.py`），缺 `open163` Cookie 实战。
- ✅ GUI 打包 exe 已验证（`python build_exe.py`），桌面版可正常启动+授权+加载营列表。
- 待办见 `docs/05-待办与下一步.md`。

## 最易做错的七条（全部细节在 `docs/11`）
6. **测试必须设 `XQD_TEST_HOME`** 隔离配置/历史/分片缓存，否则会改用户下载目录。
   ⚠️ 凭据**读取**不受它影响（真网络测试要用真实 Cookie）；
   但 `save_cookie()` 在该变量存在时**拒绝写真实凭据**，测试要验证写入须显式传 `path`。
7. **列号一律走 `xqd_gui.COL_*`**（v1.5.0 起 6 列，勾选框后第一列是「标题前缀」）；
   多营合并**不重排序号**、每行绑 `camp_of_row`。封装阶段释放**网络槽位**
   （`running_workers - network_released`），完成时记得 discard + 再释放一次。
8. **★ MuMu「no Qt platform plugin」弹窗**（反复出现，v1.5.1 根治）：
   打包 exe 的 PySide6 rthook 注入 `QT_PLUGIN_PATH=<_MEIPASS>\PySide6\plugins`（Qt6），
   子进程继承 → MuMu 的 Qt5 程序加载 Qt6 `qwindows.dll` 失败。
   修复在 `xqd_proc`（**每次创建子进程时**净化 `QT_*`/`QML*`/`_PYI_*`，
   MuMu 命令显式指向自带 Qt5 插件目录、剔 `_MEI*`/`PySide6` PATH、设 cwd），
   **别改自己进程的环境**（会弄坏自己的 Qt6 界面，且孙进程来不及）。
   GUI 再叠一层：启动优先用已保存授权、默认不调 MuMuManager，
   只有首次 / 点「重新授权」(`force_mumu=True`) 才走模拟器。细节见 `docs/11` M 节。
- 进度：核心能力全就绪（API 全链路、端到端 6/6、**GUI v1.5.1** 含多营勾选、
  标题前缀、进度恢复、封装流水线、缓存授权优先 + MuMu Qt 弹窗根治；
  离线回归 403 项全绿，exe 已打包并放桌面）。
  待办：全量 266+6 节、163 适配器实战。
  ⚠️ GUI 测试偶发 Qt 退出段错误（HEAD 原版可复现），以「失败 0」为准。
- ⚠️ **v1.5.3 tag 作废**：曾发过一次 330MB 的 Release，删除后 GitHub 拒绝同名重建。
  **下个版本用 v1.5.4**（版本号已改成 1.5.4）。

## ★ v1.5.4 完成 + 产物改名（2026-11-08）

- **去原生标题栏**：`WindowStyle=None` + `WindowChrome`（`CaptionHeight=0`）；
  `src/Xqd.Controls/WindowButton.cs` 自绘 最小化/最大化-还原/关闭（矢量 Path 图标）；
  品牌区左键可拖窗（5px 阈值区分单击）、双击切最大化；
  `WM_GETMINMAXINFO` 限制最大化不遮任务栏。
- ★★ **控件模板严禁用 `XamlReader.Parse` 解析 `<ControlTemplate.Triggers>`** ——
  抛「无法设置未知成员 ControlTemplate.Triggers」，异常在 `Show()` 的 **Measure 阶段**，
  **窗口压根创建不出来**（进程活着但 `MainWindowHandle=0`，只有 `~/.xqd_tool/gui-error.log` 留痕）。
  正确做法：模板用 `FrameworkElementFactory`，配色用鼠标事件直接改 `Background`。
  `MultiDataTrigger.Conditions` 只接受 `Condition(Binding, value)`。
- ★ **产物名统一 `xqd-downloader`**（原 `xingqudao-downloader`）：
  Release 只发**一个** `xqd-downloader-vX.Y.Z.zip`，内含 `gui/` + `cli/` + `README.txt`，
  **不含 `server/`**；`Xqd.Gui.csproj:AssemblyName` / `States.ProductExeName` 同步。
  历史文档（docs/01/10/11/12）里的旧名**不回改**。
- CI 已删 `build-python` 作业、只 publish gui+cli，版本号校验改读 `States.AppVersion`。
- ★ 本机 `dotnet build` 曾被 **360rp.exe** 锁 DLL（CS2012/MC1000/MSB3883）；
  **360 已关闭，现在仓库目录直接构建即可**。若再开启：复制 `src/ global.json ui.html`
  到 `D:\xqvN\` 独立目录构建；实机验证要放在 360 已信任目录，且用 PowerShell 工具的
  `Start-Process`（Bash 后台是 Session 0，WPF 窗口创建了也不可见）；
  HWND 检查要和启动写在同一个命令里。
- ★ **exe 名带版本号**：`xqd-downloader-vX.Y.Z.exe`（.dll/.deps.json/.runtimeconfig.json 同步）。
  csproj 用 `<PkgVersion>` 派生 `<AssemblyName>xqd-downloader-v$(PkgVersion)</AssemblyName>`，
  发布传 `-p:PkgVersion=X.Y.Z`；**不能用 `-p:AssemblyName=`**（NuGet 还原会当项目名 →
  `Ambiguous project name` 直接失败），**也不能发布后手工改 exe 名**（apphost 与
  runtimeconfig.json 配对会断）。CI 校验 PkgVersion 与 tag 一致。
- 验证：构建 0 错 0 警 / 回归 **224-0** / 实机 `WS_CAPTION=False`、三个按钮正常、无新异常日志。

## ★ v1.6.0 合并单表（2026-11-08）

- **单表 8 列**：状态(胶囊) / 课程 / 所属营 / 时长 / 大小 / 速度 / 剩余 / 进度。
  删掉「下载管理」面板、勾选框列、前后缀列、课名后状态词；
  加了视图切换 5 档、右键菜单 5 项、「重置下载记录」、表尾汇总栏、表尾历史区。
- 「下载/暂停/继续」合并为 `BtnRun`（`SyncPauseButton()` 是唯一状态来源）；
  勾选框没了以后「只下其中几节」由**行选中**承担。
- 行模型：**行 = 一节课**（`LessonRow` 唯一事实来源）；历史行单独放表尾浅灰区
  （独立 ListView + 分隔带，**不与主表混类型** —— GridView 画不出跨列分隔带）。
- 视图过滤用 `CollectionViewSource.GetDefaultView` + `Filter`；
  下载范围用 `States.InDownloadScope()` 单一判定函数（可单测）。
- 状态胶囊配色在 `States.StatePills`，画刷转换器 `Xqd.Controls/HexBrushConverter`。
- ★★ **空状态提示别用覆盖层做**：给 ListView 叠一个居中提示（Grid 包裹 +
  TextBlock）会 **STACK_OVERFLOW 退出（0xC00000FD）**，而且**不写任何错误日志**
  —— 只能从**退出码**看出来。已放弃叠层，改成提示文字放在表格正下方一行。
- 业务 API 排查要点：URL 是 `.../financial/api/transfer` + `/gate/course/xxx`，
  必须带 `Origin`/`Referer` 头；接口本身 2~5 秒响应，程序里慢是 30s 超时 ×2 重试。

## ★ v1.6.1 收敛完成（2026-11-08，HEAD `786f66b`）

- **仓库只剩 C# 一套实现**：删掉根目录 15 个 Python 实现、`archive/`、`state/`、
  `_lel/api/` 下 29 个依赖已删模块的测试脚本（89 文件 **+156/−19515**）。
- **保留**：`_lel/core/netease_mooc.py`（NOTICE 声明对象）、`_lel/api/qianliao.py`
  （网关对照稿）、`_lel/login/` `_lel/v2/`（逆向记录）—— 运行时不用但合规依赖它们。
- `ui.html` 移入 `src/Xqd.Server/`（Server 自带）。
- `QianliaoPlatform` 的 `_campIndex`/`_catalogs` **加锁**（UI 线程与下载线程会并发写
  同一个 Dictionary）★ 只锁字典读写，**不锁网络请求**。
- 三个 Release（v1.5.4 / v1.6.0 / v1.6.1）都是**唯一附件**、CI 全绿、
  解压后直接跑发布物验证过。v1.5.3 那段「一个 Release 挂两个附件」已过时。
- ★ 提交信息文件**别放仓库根目录**（`git add -A` 会带进去，删了又要 amend）；
  放工作区外更省事。

## ★ v1.6.2 公开课 + 营列表换名（2026-11-08，HEAD `c064f36`）

- **公开课能下载了**：`myCourseListV2` 不传 skyType 实测返回 **26 个营**，
  其中 **16 个 `skuType=OPEN_COURSE` 的公开课 campId=null** → 正课端点拿不到课表，
  老代码直接返回空列表 → 一直下不了。补上 **`/gate/openCourse/playListOfCourse`
  + `{periodId}`** 即打通（播放地址的 `OPEN_COURSE` 分支代码里早就有，只是走不到）。
  实测「晨练焕醒计划」27 节/1.5s。
- ★ 三个坑：① 公开课**不能按营名反查**（同名营有多个批次，如「华佗五禽戏…」×5）
  → 播放地址取错，有 periodId 就直接用；② 同名营的 **Key 必须唯一**（勾选状态按它恢复）
  → 用 `campId ?? periodId`，否则 5 个同名营共用 Key 会串号；
  ③ 课表缓存 key 也要用 `c:campId`/`p:periodId`，否则同名营互相覆盖。
- **左栏去掉固定分类表头**（全部/正式营/体验营/轻课）→ 改为按**真实营名**列出全部营，
  分「已购课程 / 公开课」两组（CollectionView GroupStyle）+ 顶部搜索框；
  同名批次加序号。「轻课」改名「公开课」。
- 回归 253 → **263**；Release `xqd-downloader-v1.6.2.zip` 366,774 B。
- ★ 截图别用 `SetWindowPos(HWND_TOPMOST)` 改窗口位置 —— 会让 WPF 自己的
  `WindowChrome._SetRoundingRegion` 抛 `Win32Exception(87)`；用 `BringWindowToTop`。

## ★★ 运行环境依赖（v1.6.3 起，重要）

**工具的硬依赖只有 ffmpeg / ffprobe**（分片转封装 + 成品时长校验）。
缺了它们课能下但合并不成 MP4。

- **首次启动自动检测** → 缺则弹「运行环境检查」窗口 → 一键自动下载安装
  （顶栏也有「环境检查」按钮可手动触发）。
- ★ **下载源优先非 GitHub 的国内 CDN**：阿里 npmmirror（`ffmpeg-static`
  的**独立 win32-x64 `.gz`**，.NET `GZipStream` 原生解压，无需 tar/7z）
  → ffmpeg 官方构建站 gyan.dev → 带代理的 GitHub 源（ghfast.top / gh-proxy.com）。
  **ghproxy.net / 华为云 / 腾讯云 / btb4g 实测不可用**。
- 装到 `~/.xqd_tool/ffmpeg/bin`（用户目录，不写 PATH、不要管理员权限）；
  `MediaProbe.FindTool` / `ExistingChecker.FfprobeExe` 把自装目录排在**最前**。
- 命令行静默安装：`xqd-downloader-vX.Y.Z.exe --install-deps`（幂等，退出码 0=成功）。
- ★ **.NET 8 桌面运行时不在发行包里**（自包含单文件/目录都是 162 MB，太大）。
  靠 `gui/启动.bat`（GBK+CRLF 的纯 cmd 脚本）检测引导 + README/Release 给下载链接。
  判据必须是 `Microsoft.WindowsDesktop.App 8.`（只有 NETCore.App 不够，WPF 要桌面运行时）。
- ★ `.bat` 写文件用 `encoding='gbk', newline='\r\n'`；`.gitattributes` 补
  `*.bat text eol=crlf`（全局 eol=lf 会毁掉批处理的 goto）。

## ★ 代码结构（见 `docs/12`）

★ **v1.6.1 起仓库只剩 C# / WPF 一套实现**（Python 版、`archive/`、`state/`
已删除；`_lel/` 只留合规与分析材料 —— `core/netease_mooc.py` 是 NOTICE 声明对象、
`api/qianliao.py` 是网关对照稿、`login/` `v2/` 是逆向记录）。

`src/Xqd.sln` 六项目：`Xqd.Core`（契约/引擎/鉴权/历史/去重/163 内核）·
`Xqd.Controls`（WPF 控件库）· **`Xqd.Gui`（★ 桌面工具，单表 8 列）** ·
`Xqd.Server`（网页版，自带 `ui.html`）· `Xqd.Cli`（CLI）· `Xqd.Tests`（离线回归）。
本地产物 `dist-csharp/gui/xqd-downloader-vX.Y.Z.exe`。
两种数据源靠 `--mode` 切换：`api`（默认，**不需要模拟器**）/ `adb`（旧路径）。
API 模式不需要 sweep，播放地址现场解析，`t` 每次都变 → 签名天然新鲜。
**课名不靠播放反推**（课表一次拿全）。

## ★ 业务 API（已全链路打通，详见 `docs/09`）

`POST https://m.qianliao.net/financial/api/transfer` + `/gate/course/<endpoint>`，
Body `{"transferData":{...}}`

- **成功码在 `state.code`**（不是顶层 `code`）—— 读顶层永远 None，会误判打不通。
- **必须 `ProxyHandler({})` 禁用系统代理**，否则被代理吞掉返回 HTML。
- **必须带 `Origin: https://m.qianliao.net` 与 `Referer` 头**，否则网关返回
  `404 Not Found`（Spring Boot 错误结构：`timestamp/status/error/path/sysTime`）。
- 端点（前缀 `/gate/course/`）：营列表 `myCourseListV2`（`skyType`：`FINANCIAL`→9 正式营、
  `INTENTION`→1 体验营、不传→26 含公开课）、课表 `playListOfCourse`、播放地址
  `getCoursePlayUrl`（`businessType`=`camp`/`OPEN_COURSE`）。
- 实测响应 2~5 秒；程序里慢是 30s 超时 × 2 次重试（网络不稳，非代码问题）。