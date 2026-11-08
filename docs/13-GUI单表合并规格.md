# GUI 改版规格 + 技术栈收敛：v1.5.4 无边框 → v1.6.0 单表合并 → v1.6.1 只留 C#

> 本文是**施工图**。规格由用户逐条确认后定稿（2026-11-08 讨论）。
>
> ## ★ 重大调整（2026-11-08 14:10 定论）
>
> **技术栈收敛为只保留 C# / WPF。**
>
> - ❌ **不回滚**到 `csharp-wpf` 分支 —— 回滚会丢掉 6 个提交，其中
>   `acddefa`（拆 `Xqd.Controls` 类库，根治 MC3074）、`27ccffa`（XAML 补
>   `;assembly=` + `global.json`）、`b6cb76f`（CI 中国时区 + ffmpeg 查找桩）
>   **是干净 runner 构建的必需项**，回滚必然导致 CI 失败。
> - ✅ **在当前 master 上做减法**：删 Python 实现，保留 C# 与全部 CI 修复。
> - ✅ **以后只改 C# 一份**，工作量减半，且不会出现两版行为不一致。
>
> **Server / CLI 不再随 Release 发布**，留在源码里，需要的人从源码跑。
>
> ### ★ Release 产物命名（2026-11-08 14:30 追加）
>
> 产物名从 `xingqudao-downloader` 统一改成 **`xqd-downloader`**（与仓库名
> `chisenin/xqd-downloader` 对齐，短、纯 ASCII、少 8 个字符）。
>
> | 位置 | 新名字 |
> |---|---|
> | Release 附件 | `xqd-downloader-vX.Y.Z.zip`（**一个**附件） |
> | zip 内主程序 | `gui/xqd-downloader-vX.Y.Z.exe`（**带版本号**） |
> | zip 内 CLI | `cli/Xqd.Cli.dll` |
> | 源码常量 | `States.ProductExeName`（产品名基址） / `Xqd.Gui.csproj` 的 `PkgVersion` |
>
> zip 内容 = `gui/` + `cli/` + `README.txt`，**不含 `server/`**。
>
> **exe 带版本号的实现方式**：`Xqd.Gui.csproj` 里
> `<AssemblyName>xqd-downloader-v$(PkgVersion)</AssemblyName>`，
> 发布通道传 `-p:PkgVersion=X.Y.Z`。`.dll` / `.deps.json` / `.runtimeconfig.json`
> 随之同步改名，产物自洽。
> ⚠️ **不要用 `-p:AssemblyName=`** —— 它是 MSBuild 全局属性，会被 NuGet restore
> 当成项目名 → `Ambiguous project name` 直接失败。
> ⚠️ **也不要 publish 完再手工改 exe 名** —— apphost 与 `.runtimeconfig.json`
> 的配对一旦断掉，程序直接起不来。
>
> ⚠️ 历史文档（`docs/01` `docs/10` `docs/11` `docs/12`）里的
> `xingqudao-downloader-*` 是**当时真实的产物名**，属历史记录，**不回改**。
>
> ⚠️ 改名不影响 XAML 程序集解析：当前 XAML 引用的是 `;assembly=Xqd.Controls`
> （`acddefa` 拆出的类库），与主程序 `AssemblyName` 无关。
>
> ---
>
> ## 版本序列与执行顺序
>
> | 序 | 版本 | 内容 | 风险 | 依赖 |
> |---|---|---|---|---|
> | 1 | **v1.5.4** ✅已发布 | 去掉 Windows 原生标题栏，顶栏右侧自绘窗口按钮 | 低（外观层） | 无 |
> | 2 | **v1.6.0** ✅已实现 | 课程列表 + 下载管理合并为单表（8 列） | 高（结构层） | v1.5.4 已验证 |
> | 3 | **v1.6.1** ✅已实现 | 删 Python 实现与 archive/，CI 只发 C# 一个附件 | 低（删除层） | v1.6.0 已验证 |

> | 4 | **v1.6.2** ✅已实现 | 公开课可下载 + 营列表按真实营名分组（去固定分类表头） | 中（业务+界面） | v1.6.1 已验证 |
>
> ---
>
> # 第三部分：v1.6.2 —— 公开课与营列表改版
>
> ## 一、为什么改
>
> 1. **公开课下不了**：营列表只取「正式营 / 体验营」，`myCourseListV2` 不传 skyType
>    实际会带回 26 个营，其中 **16 个是 `skuType=OPEN_COURSE` 的公开课**
>    （才艺名师公开课、节气养正公开课、晨练焕醒计划…）—— 它们**没有 campId**，
>    正课端点 `playListOfCourse` 拿不到课表，代码里直接返回空列表，于是下不了。
> 2. **表头写死分类名格格不入**：左栏固定「全部 / 正式营 / 体验营 / 轻课」四个胶囊，
>    但用户的营叫「摄影课」「美容课」时，这些分类名毫无意义。**营名本身就是最好的分类。**
>
> ## 二、公开课怎么支持
>
> | 项 | 正课 | 公开课 |
> |---|---|---|
> | 标识 | `campId`（有） | `campId` 为空，靠 `periodId` |
> | 课表端点 | `/gate/course/playListOfCourse` `{campId}` | **`/gate/openCourse/playListOfCourse` `{periodId}`** |
> | 播放地址 | `businessType=camp` + `businessId=campId` | `businessType=OPEN_COURSE` + `businessId=periodId` |
>
> - 播放地址那段逻辑**代码里早就有**（`ResolveAsync` 的 `OPEN_COURSE` 分支），
>   只是因为课表拿不到而永远走不到 → 本次补上课表端点即可打通。
> - 实测：`晨练焕醒计划` periodId=170814973572 → **27 节**（与 `courseTotalNum` 一致），1.5 秒。
> - 「轻课」在 App 内确实是空的 → 该入口**改名「公开课」**。
>
> ★ **两个必须注意的坑**：
> 1. **不能按营名反查公开课**：同名营有多个批次（「华佗五禽戏…」×5），
>    反查会取到别的营 → 播放地址取错。公开课有 `periodId` 时**直接用它**，别反查。
> 2. **同名营的 Key 必须唯一**：勾选状态按 Key 恢复，公开课没有 campId，
>    退回用营名会让 5 个同名营共用一个 Key → 勾选串号。**改用 periodId**。
>
> ## 三、营列表怎么改
>
> - **去掉**「全部 / 正式营 / 体验营 / 轻课」四个固定分类表头。
> - 左栏改为**按真实营名**列出全部营，分「**已购课程 / 公开课**」两组（`GroupStyle` 组标题）。
> - 顶部加**搜索框**（26 个营需要搜索，按营名过滤）。
> - 同名批次加序号区分：「华佗五禽戏·肩脊舒身营-T (2)」。
> - 付费营排在前面（分组标题顺序也跟着它）。
>
> ---
>
> ★ **v1.6.0 实现说明**：
> - 8 列 = 状态(胶囊) / 课程 / 所属营 / 时长 / 大小 / 速度 / 剩余 / 进度
> - 「下载」/「暂停」/「继续」合并为 `BtnRun`（状态唯一来源 = 引擎队列）
> - 勾选框删除后由**行选中**承担「只下其中几节」；视图切换 5 档只过滤显示
> - 历史行（不在当前课表）单独放表尾浅灰区，不参与下载范围
> - 任务状态直接写回课程行 → `TaskRow` 类与 `Job.TaskRow` 已删除
> - 遗留：`QianliaoPlatform._catalogs` 多营并发无锁写入，仍待补锁
>
> **为什么是这个顺序**：
>
> - **v1.5.4 排最前**：纯外观、零结构依赖，先跑热构建/打包流程，
>   拿一个能立刻看到成果的版本。
> - **v1.6.0 居中**：结构重构主体，此时外观层已稳定，不会被推翻。
> - **v1.6.1 收尾**：删代码是「减法」，风险最低；放最后可确保前面的
>   改动都在只有 Python 存在的基线上验证过，**不会删掉正在开发的代码**。
>
> ## ★ 原「v1.5.5 启动异步化」已取消
>
> 核实后发现：**C# 版本来就是全异步的**（`LoadCampsAsync` /
> `CatalogWorkerAsync`，单营多营统一走后台 worker，**没有同步分支**）。
> 「单营同步拉课表卡 UI 线程」是 **Python 版独有**的问题。
> 技术栈收敛到 C# 后，这个问题自动消失，**不需要单独的 v1.5.5**。
>
> ⚠️ 但 C# 版仍有一处待改进：`QianliaoPlatform._catalogs` 缓存 dict
> 在多营并发时无锁写入（Python 版同样问题）。v1.6.0 改行结构时
> 一并加锁 —— **先改缓存结构，后改行结构**，反过来要在行结构里塞并发补丁。

## 〇、涉及范围

| 版本 | 涉及文件 |
|---|---|
| v1.5.4 | `src/Xqd.Gui/MainWindow.xaml(.cs)`、`src/Xqd.Gui/Resources/Theme.xaml` |
| v1.6.0 | `src/Xqd.Gui/MainWindow.xaml(.cs)`、`src/Xqd.Gui/ViewModels/*.cs`、`src/Xqd.Core/States.cs`、`src/Xqd.Core/Naming.cs`、`src/Xqd.Core/Api/QianliaoClient.cs`、`src/Xqd.Tests/Program.cs` |
| v1.6.1 | 根目录 `xqd_*.py`、`build_exe.py`、`ui.html`、`archive/`、`.github/workflows/release.yml`、`README.md`、`NOTICE.md`、`RELEASE_NOTES.md`、`docs/12` |

---

# 第一部分：v1.5.4 —— 去掉原生标题栏

## 目标

去掉 Windows 原生标题栏（那行含最小化/最大化/关闭的灰色条），
在顶栏（蓝色渐变区）最右端补一组自绘的窗口按钮。

## 决策

- ❌ **不做 logo 区右键系统菜单**（评估后否决：用户找不到关闭按钮的风险）。
- ✅ **顶栏最右端自绘一组最小化 / 最大化 / 关闭按钮**。
- ✅ logo 区左键**单击**仍打开「使用说明与关于」（行为不变）。
- ✅ logo 区**按住左键拖动**可移动窗口；**双击**切换最大化/还原。

## 必须处理的连带影响（无边框窗口的固有坑）

| 问题 | 处理方式 |
|---|---|
| 没有标题栏 → 窗口不能拖动 | 顶栏空白处 + logo 区支持左键拖动（`DragMove()` / PySide6 `startSystemMove()`） |
| 左键拖动与「单击打开说明」冲突 | **用位移阈值区分**：按下后移动 > 5px 判定为拖动（不打开对话框）；未移动则视为单击 |
| 双击不会自动最大化 | 自己实现：双击切换 `WindowState`（最大化 ↔ 还原） |
| 最大化会盖住任务栏 | 处理 `WM_GETMINMAXINFO`，给最大化窗口留出任务栏高度（`MonitorArea` / `WorkArea`） |
| 窗口边缘没有 DWM 阴影，显得"贴纸化" | 用 `WindowChrome` 保留阴影与缩放边框（`CaptionHeight=0` + `GlassFrameThickness=0`） |
| 缩放边框（resize handle）消失 | `WindowChrome` 的 `ResizeBorderThickness` 保留可拖拽边缘；PySide6 用 `QSizeGrip` 补一个右下角拖拽把手 |

## 自绘按钮规格

- 位置：顶栏（蓝色渐变区）**最右端**，三个按钮一组。
- 尺寸：每个约 44×46（命中区够大，13px 字体下点得准）。
- 外观：默认透明，鼠标悬停时浅色半透明底；
  **关闭按钮悬停用红色底 + 白色图标**（Windows 惯例）。
- 图标：细线条矢量（`Path`），**不用图片资源**（避免多资源文件与部署问题）：
  最小化 = 一横线；最大化 = 方框；还原 = 两个错位方框；关闭 = 交叉。
- 最大化状态下，最大化按钮**图标切换为「还原」**。

## 涉及文件

**C# WPF 版**
- `src/Xqd.Gui/MainWindow.xaml` — `WindowStyle="None"` + `WindowChrome`；
  顶栏加窗口按钮组；logo 区挂 `MouseLeftButtonDown` / `MouseMove` / `MouseDoubleClick`
- `src/Xqd.Gui/MainWindow.xaml.cs` — 拖动阈值判定、双击最大化、按钮事件、`WM_GETMINMAXINFO`
- `src/Xqd.Gui/Resources/Theme.xaml` — 窗口按钮样式（普通 / 悬停 / 关闭悬停）

**Python 版**
- ~~`xqd_gui.py`~~ —— **技术栈收敛后不需要**（见第三部分 v1.6.1）。

## 验收

- 窗口无原生标题栏，顶栏右端有三个自绘按钮。
- 拖动、双击最大化、右键任务栏菜单（还原/移动/大小/关闭）均正常。
- **最大化后不遮挡任务栏**。
- 关闭按钮能正常退出（`OnClosing` 里的 `_appCts.Cancel()` / `FlushHistory()` / `SaveCfg()` 仍执行）。

---

# 第二部分：v1.6.0 —— 课程列表与下载管理合并为单表

## 一、为什么要改

原界面右栏是三块：课程列表（上）、下载管理（中）、运行日志（下）。
前两块的行**不是同一个集合**：

| | 行来源 | 生命周期 |
|---|---|---|
| 课程列表 | 营课表 `playListOfCourse` | 每次选营重建 |
| 下载管理 | 任务 Job + **磁盘历史**（跨会话） | 可含「本次课表没有、上次下过」的课 |

两者在**课名、进度、状态词**上重复显示，用户要在两个表之间来回对照。
合并后行 = 一节课（`LessonRow` 为唯一事实来源），任务信息作为该行的附加列。

### ★ 核心矛盾与解法

历史里存在、但不在当前课表中的课**追加到表尾**，用浅灰分隔带标
「上次下载 · 不在当前课表中」。这些行灰色显示、不可下载，营名取自历史记录。

## 二、表格结构（8 列）

| # | 列 | 内容 | 备注 |
|---|---|---|---|
| 0 | 状态 | 解析中/下载中/封装中/校验中/排队中/已暂停/已完成/失败/已存在/需重下 | **独立成列**，独立配色 |
| 1 | 课程 | 课名 | 宽度最大 |
| 2 | 所属营 | 营名 | **单营时隐藏**，多营合并时必需 |
| 3 | 时长 | MM:SS / H:MM:SS | 唯一只能从课表拿的元信息 |
| 4 | 大小 | `42.0/145 MB`（下载中）/ `128.4 MB`（完成）/ `—`（空闲） | 右对齐 |
| 5 | 速度 | `5.0MB/s` / `—` | 右对齐 |
| 6 | 剩余 | `00:31` / `—` | 右对齐 |
| 7 | 进度 | 进度条 + 百分比数字 | 两份进度合一 |

**被删除的元素**（务必清理干净，别留死代码）：

- 勾选框列（课程列表的 `IsChecked` / `COL_CHECK`）
- 标题前缀列（`ColPrefix` / `COL_PREFIX`）—— 序号仍写进成品文件名，只是不显示
- 标题后缀列（`ColSuffix` / `COL_SUFFIX`）—— 日期同上
- 课名后的方括号状态词（`StateSuffix`）→ 由独立状态列取代
- 「全选」「清空」「下载选中」「下载此课」按钮
- 「清除列表」「删除文件」按钮
- 整个「下载管理」面板（`LstTasks` / `TaskRow` 列表）

**新增**：状态列、所属营列、大小/速度/剩余三列、视图切换器、右键菜单、
「重置下载记录」按钮、表尾汇总栏。

> ★ **文件名规则完全不动**：`Naming.LessonStem` 仍是 `<序号>.<课名>.<日期>`，
> 序号和日期照旧写进成品文件名。相关单测见 `docs/01-已验证事实.md`。

## 三、工具条与菜单

### 3.1 工具条（从左到右）

```
[全部][待下载][下载中][已完成][失败] │ [画质 ▾] [重新检测] [下载/暂停] │ [重置下载记录]
```

- 视图切换 5 档：**全部 / 待下载 / 下载中 / 已完成 / 失败**。
  只过滤显示，**不影响下载范围判定**。
- 「重置下载记录」= 清任务表 + 清历史 + 复位状态标记，**不动磁盘文件**。
- 原「下载管理」标题旁的全局汇总（`剩余约 12:30 · 3 个在跑 / 20 个排队`）
  **移到表尾汇总栏**，否则这条信息会丢。

#### ★ 下载与暂停合并为一个按钮

原「下载」「暂停」两个独立按钮合并成**一个状态切换按钮**：

| 当前状态 | 按钮显示 | 点击后 |
|---|---|---|
| 空闲（无任务运行） | **下载**（主色蓝） | 开始下载 → 立即变成「暂停」 |
| 正在下载 | **暂停**（琥珀色） | 暂停全部下载 → 立即变成「继续」 |
| 已暂停 | **继续**（琥珀色） | 从断点续传 → 立即变成「暂停」 |

- 按钮在切换状态时**同步换文案与配色**（下载=蓝、暂停/继续=琥珀）。
- 「暂停」保留原语义：**停住全部下载，已下好的分片保留**，可续传。
- 状态来源：引擎的任务队列状态（有无运行中 / 队列中有已暂停任务）。
- ⚠️ 状态判定与原有 `BtnPause` 的 `IsEnabled` 逻辑合并，**不要出现两个来源**。
  引擎里暂停/继续是同一个操作（`pause` flag 取反），按钮只是调不同入口。

### 3.2 右键菜单（表格行上）

| 菜单项 | 作用 |
|---|---|
| 下载此课 | 只下这一节 |
| 重试此课 | 对失败/需重下的行重排队 |
| 删除成品文件 | 移到 `_已删除` 子目录，**失败要弹错不静默** |
| 复制文件名 | 复制成品全名到剪贴板 |
| 打开所在文件夹 | 已在磁盘上时才可用 |

## 四、行为规则

| 场景 | 规则 |
|---|---|
| 点「下载」 | **有选中行 → 只下选中的；无选中 → 下当前筛选视图内所有待下载的课** |
| 下载范围排除 | 自动跳过 `已存在` |
| 失败/需重下 | 点「下载」时**自动包含**（重排队重下），不需手动勾选 |
| 双击行 | 只下这一节 |
| 删除成品 | 移到 `_已删除` 子目录（沿用现有行为），失败弹错 |
| 历史行 | 表尾、灰色、不可下载、不参与下载范围判定 |
| 视图切换 | 只过滤显示 |
| 营多选 | 左栏营列表的勾选框**保留**（"选哪些营"与"选哪几节课"不同层级） |

### ★ 行选中的接替作用

去掉勾选框后，「只下其中几节」的能力**改由行选中（Ctrl/Shift 多选）承担**：
选中若干行 → 点「下载」只下选中的；不选 → 全下当前视图。
不新增任何控件。

## 五、视觉规格

配色沿用现有主题（`src/Xqd.Gui/Resources/Theme.xaml`）：

| 项 | 规格 |
|---|---|
| 表头 | **文字全部居中**，`#4A5A72` 半粗 13px，底色 `#EEF2F8` |
| 状态列 | **胶囊标签**：浅底 + 同色系深字 + 0.5px 描边，高 20px |
| 进度 | 条 40px + 右侧百分比数字；**条按状态着色**（下载中蓝/封装中橙/完成绿/失败红） |
| 数字列 | 大小/速度/剩余**右对齐**；空闲值 `—` 浅灰 `#C3CBD8`（不用空白，避免像渲染漏了） |
| 所属营 | 灰色 `#8494A8`，弱化处理，别跟课名抢注意力 |
| 课名 | `#2B3445` 13px，**不加粗**（266 行加粗会很吵） |
| 行高 | 30px |
| 表尾汇总栏 | 左：分类计数；右：全局 ETA（蓝色半粗）；底色 `#F4F6FA` |
| 历史分隔带 | `#F4F6FA` 浅底 + 22px 分隔带 + 小字说明，**不要重色横线**（会把表格切碎） |
| 斑马纹 | `#FAFBFD` 极浅，保留 |
| 日志区 | 高度 180px → **140px**，腾给合并后的大表 |

### 状态胶囊配色（底 / 字 / 描边）

| 状态词 | 底 | 字 | 描边 |
|---|---|---|---|
| 已存在 / 已完成 | `#EAF3DE` | `#3B6D11` | `#97C459` |
| 下载中 / 解析中 | `#E6F1FB` | `#185FA5` | `#378ADD` |
| 封装中 / 校验中 / 已暂停 | `#FAEEDA` | `#854F0B` | `#BA7517` |
| 排队中 | `#EEEDFE` | `#534AB7` | `#7F77DD` |
| 失败 / 需重下 | `#FCEBEB` | `#A32D2D` | `#E24B4A` |

历史行统一用 `#F1F3F6` 底 + `#7D8B9C` 字。

## 六、实现要点

1. **列号一律走常量**（`States.Col*`），界面与测试一律引用，
   不要写死数字。列号重排后**必须同步改单测里的断言**
   （`src/Xqd.Tests/Program.cs` 约 162-164 行引用了旧列号 —— 这是最易漏的点）。
2. **状态词表单一来源**：`States.StateTexts` / `States.StateColors`。
   状态列胶囊颜色由同一份状态词驱动，**漏一个词就少一种配色**。
3. **状态更新走同一套**：原来有「课名后状态词」和「下载管理状态列」两处，
   合并后只剩状态列一处 —— 状态变更的通知路径要一并收敛。
4. **进度口径统一**：有 Job 用 Job 实时进度，否则用
   历史 / 分片缓存 / 磁盘检测 四个来源（课程列表原本就是这个口径，下载管理那列合并掉）。
5. **文件名生成不动**：`Naming.LessonStem` 保持原样。
6. **右对齐**：`GridViewColumn` 的 `CellTemplate` 里用 `TextAlignment="Right"`。
7. **课表缓存加锁**：`QianliaoClient` 的课表缓存 dict 在多营并发时
   无锁写入，v1.6.0 一并加锁（只锁缓存读写，不锁网络请求）。

## 七、涉及文件

> ★ **只改 C# 版**（技术栈收敛后不再同步 Python 实现）。

**C# WPF 版**
- `src/Xqd.Core/States.cs` — 列常量重排 + 胶囊配色表
- `src/Xqd.Gui/MainWindow.xaml` — 表格结构、工具条、右键菜单、汇总栏
- `src/Xqd.Gui/MainWindow.xaml.cs` — 视图切换、下载/暂停语义、菜单事件
- `src/Xqd.Gui/ViewModels/LessonRow.cs` — 去掉 `IsChecked`/`Prefix`/`Suffix`/`StateSuffix`，
  加 `Camp`/`Size`/`Speed`/`Eta`/`Progress`/`StateWord`
- `src/Xqd.Gui/ViewModels/TaskRow.cs` — 合并进 LessonRow 后删除
- `src/Xqd.Gui/Resources/Theme.xaml` — 胶囊样式、进度条着色
- `src/Xqd.Core/Api/QianliaoClient.cs` — 课表缓存加锁（多营并发写）
- `src/Xqd.Tests/Program.cs` — 列号断言

## 八、验收

- C# Release 构建 0 错 0 警，实机启动界面正常。
- 视图切换、下载范围判定、失败自动重试、删除成品，四项行为正确。
- 成品文件名格式与改动前完全一致（`<序号>.<课名>.<日期>.mp4`）。
- `Xqd.Tests` 离线回归全绿。

---

# 第三部分：v1.6.1 —— 技术栈收敛为只留 C#

## 目标

仓库里**只剩 C# / WPF 一套实现**。Release 只发一个 C# 附件。

## ⚠️ 绝对不要用 `git reset --hard csharp-wpf`

回滚到 `csharp-wpf` 分支会丢掉这 6 个提交，其中三个是**干净 runner 构建的必需项**：

| 提交 | 内容 | 丢了会怎样 |
|---|---|---|
| `27ccffa` | XAML 补 `;assembly=Xqd.Controls`、`global.json` 锁 SDK、CI UTF-8 | CI 构建失败（MC3074 复发） |
| `acddefa` | 拆出 `src/Xqd.Controls` 类库 | **CI 构建失败** —— 根治 MC3074 的关键 |
| `b6cb76f` | CI 补中国时区 + ffmpeg/ffprobe 查找桩 | C# 离线回归在 runner 上必挂 |
| `13e5acc` | Python 依赖锁 Essentials | 不需要（Python 要删） |
| `f27ef3f` | CI 兼容 immutable release | 建议保留 |
| `95b4f7b` | 记录 immutable release 限制 | 建议保留 |

**正确做法：在当前 master 上做减法**（`git rm` / 删除文件），不碰历史。

## 删除清单

| 路径 | 处理 | 理由 |
|---|---|---|
| `xqd.py` `xqd_api.py` `xqd_app.py` `xqd_auth.py` `xqd_batch.py` `xqd_creds.py` `xqd_dedupe.py` `xqd_engine.py` `xqd_gui.py` `xqd_history.py` `xqd_pdl.py` `xqd_platform.py` `xqd_proc.py` `xqd_server.py` | **删** | Python 实现主体，C# 版已全量覆盖 |
| `build_exe.py` | **删** | PyInstaller 打包脚本（CI 改后不再需要） |
| `ui.html` | **删** | Python 网页版前端，Server 不再发布 |
| `archive/`（整个目录，210K） | **删** | 历史脚本归档：`drm-analysis/` `legacy-docs/` `oneshot/` `probes/` `xwz-v2/` —— 一次性分析与实验脚本，无运行价值 |
| `dist/` `dist-csharp/` `build/` | **删** | 构建产物（已在 .gitignore，本地残留） |
| `NUL` | **删** | Windows 误建的空文件 |
| `_lel/`（1.6M） | **保留** | ⚠️ 见下方合规说明 |

### ★ 为什么保留 `_lel/`

C# 版**代码不依赖** `_lel/`（只在注释和「关于」对话框里提到路径），
但 `NOTICE.md` 明确声明了 `_lel/core/netease_mooc.py`、
`_lel/login/`、`_lel/v2/` 的来源与授权边界 —— 这是**合规声明的一部分**。

`src/Xqd.Core/Crypto/Netease163.cs` 是 `_lel/core/netease_mooc.py` 的等价移植，
NOTICE 里也写了「延续上文第二节的边界」。删掉 `_lel/` 会让这段声明失去依托。

**决策：保留 `_lel/`**，体积仅 1.6M，成本可忽略。

## 需同步修改的文件

### `.github/workflows/release.yml`
- **删掉 `build-python` 整个作业**（PyInstaller 那套）。
- `release` 作业的附件校验从 2 个改成 1 个（只认 zip）。
- 发行说明模板改成只描述 C# 版。
- `PYTHONIOENCODING` / `PYTHONUTF8` 环境变量**保留**（C# 作业的
  `dotnet` 输出也可能含中文，且删了更保险）。
- `global.json`、`TZ: Asia/Shanghai`、ffmpeg 查找桩**全部保留**。

### `README.md`
- 删掉「方式二：本地网页版」「方式三：CLI 全量批处理」的**发布下载**表述，
  改为「源码内提供，用法见下」—— **代码保留，只是不再随 Release 分发**。
- 三种前端 → 只讲 GUI 为主，Server/CLI 标注「源码内提供，需自行 `dotnet run`」。
- 架构图去掉 Python 那几层。

### `NOTICE.md`
- 第一节「运行时依赖的第三方组件」删掉 PySide6 / pycryptodome / Python
  （C# 版不用；pycryptodome 若 163 解密已移植到 C# 则一并删）。
- 第五节改写：不再提「两套实现同在 master」，只讲 C#。
- 保留 `_lel/` 的合规声明与「C# 实现不含其客户端代码」的边界。

### `RELEASE_NOTES.md` / `docs/12-项目现状与合规.md`
- 同步改为「只保留 C# 实现」的现状描述。

### `src/Xqd.Gui/Controls/HelpAboutWindow.cs`
- 「关于」对话框里提到 `_lel/core/netease_mooc.py` 的段落**保留**
  （合规声明），但措辞要调整为「C# 实现是 `_lel/` Python 实现的等价移植」。

### 版本号同步点（CI 会校验，漏了直接失败）
- `src/Xqd.Core/States.cs` → `AppVersion`
- `src/Xqd.Tests/Program.cs` → 断言里的版本号

（Python 版的 `xqd_gui.APP_VERSION` 与 `_lel/api/test_mumu_env.py` 随文件一起删除。）

## Release 附件最终形态

```
Release vX.Y.Z
└── xingqudao-downloader-vX.Y.Z.zip
    ├── gui/xingqudao-downloader.exe    ← 桌面工具（日常使用，双击启动）
    ├── cli/Xqd.Cli.dll                 ← CLI 全量批处理（源码内提供的能力，随包）
    └── README.txt
```

- **只发这一个 zip**，不再有 Python exe。
- zip 内含 `gui/` + `cli/`（**不含 `server/`** —— 网页版不再发布）。
- `README.txt` 说明：需系统已装 .NET 8 桌面运行时；ffmpeg/ffprobe 需在 PATH；
  请整目录解压后一起拷贝。

## 验收

- CI 跑通，`Xqd.Tests` 离线回归全绿，产出单个 zip。
- 本地 `dotnet build src/Xqd.sln -c Release` 0 错 0 警。
- 仓库里搜不到任何 `xqd_*.py` 引用（`docs/` 里的历史说明除外）。
- `NOTICE.md` 的声明与仓库实际内容一致（不能声明已删除的文件仍存在，
  也不能漏掉仍存在的 `_lel/`）。

