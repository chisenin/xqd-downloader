# 兴趣岛视频下载器 v1.5.3 发行说明

> **v1.5.3 是一次工程结构变更，功能代码无改动。**
> Python 与 C# / WPF 两套实现合并到同一个 `master` 分支，
> 打包与编译改由 GitHub Actions 完成，本机不再产出二进制。
>
> ⚠️ **状态：尚未发布（2026-11-08）。** GitHub Actions 已成功构建出正确产物
> （exe 104,454,314 B / zip 531,234 B），但 `v1.5.3` 这个 tag 已被一次
> **immutable release** 占用：删除 Release 后 GitHub 仍拒绝用同名 tag 重建。
> 按用户决定暂不发布；待确定新版本号后统一替换 4 处版本号并重新打 tag 触发工作流。
>
> ⚠️ 仅供个人将**自己已购**的课程备份到**自有设备**使用；导出后请及时删除。

## 本版本改了什么

| 项 | v1.5.2 及以前 | v1.5.3 |
|---|---|---|
| 分支 | `master`（Python）/ `csharp-wpf`（C#）分开维护 | **合并到 `master`**，两套源码同仓 |
| 发版 | 两个独立 Release：`v1.5.2`、`v1.5.2-csharp-wpf` | **一个 Release 挂两个附件**（待发布，见顶部状态） |
| 构建 | 本机 PyInstaller 打包 + 本机 `dotnet publish` | **GitHub Actions（Windows runner）** |
| 二进制 | 手工 `gh release upload` | 工作流自动上传，仓库不含 exe / zip |

旧分支与 v1.5.2 两个 Release **保留作历史**，不再更新。
版本号统一到 `1.5.3`：`xqd_gui.APP_VERSION`、`States.AppVersion`，
以及两处离线回归的版本断言。

## 预期附件（待发布）

| 附件 | 实现 | 实测体积 | 说明 |
|---|---|---|---|
| `xingqudao-downloader-v1.5.3.exe` | Python / PySide6 | 104,454,314 B | PyInstaller 单文件，双击即用、绿色免安装 |
| `xingqudao-downloader-v1.5.3.zip` | C# / WPF（.NET 8） | 531,234 B | 目录发布，**解压后整目录拷贝**，双击 `gui/xingqudao-downloader.exe` |

上述体积是 GitHub Actions 产物实测值；改用新版本号时文件名中的版本后缀同步替换。
两个附件的 **SHA-256 由工作流在上传时自动写进 Release 正文**（见
`.github/workflows/release.yml` 的 `release` 作业），本地不再手工记录哈希。

运行依赖：

- 两个版本都需要 `ffmpeg` / `ffprobe`（PATH 或引擎回退目录）。
- C# 版需要系统已安装 **.NET 8 桌面运行时**（`Microsoft.WindowsDesktop.App 8.x`），
  不随 zip 分发；不要只拷单个 exe，`Xqd.Core.dll`、`*.runtimeconfig.json` 等是必需的。
- 凭据只在运行时从 `XQD_COOKIE` / `%USERPROFILE%\.xqd_tool\cookie.txt` 读取，
  **仓库与发行包都不含任何账号信息**。

## GitHub Actions 工作流

文件：`.github/workflows/release.yml`。推送 tag `vX.Y.Z` 触发，四个作业：

1. `prepare` — 解析并校验版本号 `X.Y.Z`。
2. `build-python` — `windows-2022`，Python 3.13 + **`PySide6-Essentials==6.12.0`** +
   `pyinstaller==6.22.3`；先校验 `APP_VERSION` 与 tag 一致、Qt DLL 总量 < 150 MiB，
   再跑 `build_exe.py`。
3. `build-csharp` — `windows-2022`，.NET 8 SDK；`dotnet build` 全解决方案 +
   离线回归 `Xqd.Tests`，再 `dotnet publish` 三个前端（`gui/` `server/` `cli/`），
   去掉 `.pdb` 后压缩成 zip。
4. `release` — 汇总两个附件，生成含 SHA-256 的发行说明，用 `GITHUB_TOKEN`
   （`permissions: contents: write`）创建 / 更新单个 Release。

也支持 `workflow_dispatch` 手动填版本号重跑；Release 已存在时覆盖附件并更新说明。

发版步骤：改两处版本号 → 提交并推 `master` → `git tag vX.Y.Z && git push origin vX.Y.Z`。
详见根目录 `README.md`「GitHub Actions 发版」。

## 验证

- 合并后 `master` 同时保留全部 Python 源码（`xqd_*.py`、`_lel/`、`ui.html`）
  与全部 C# 源码（`src/Xqd.sln` 六项目、约 1.1 万行）。
- C# 离线回归版本断言同步到 1.5.3；Python 离线回归版本断言同步到 1.5.3。
- 工作流 YAML 与内嵌脚本语法已解析校验；实际构建结果以 GitHub Actions 运行记录为准。
- 首次 CI 运行暴露并修复两个「干净构建专属」问题：runner 控制台 cp1252 导致
  `build_exe.py` 打印中文崩溃（→ 强制 UTF-8）；XAML 引用同程序集控件报 MC3074
  （→ 拆出 `Xqd.Controls` 类库，XAML 从引用程序集解析；另加 `global.json` 锁定 SDK 8.0.x）。
  CI 另需把 runner 设成中国时区、为离线回归提供 ffmpeg/ffprobe 的 PATH 查找桩；
  Python 依赖锁定 `PySide6-Essentials`（完整元包会让 exe 从 96 MB 膨胀到 330 MB）；
  GitHub immutable release 不允许覆盖附件，同版本重跑先删 Release 再重建。
  详见 `docs/11-工具实现要点.md` O 节。
- ⚠️ **未做真网络全量下载**（网络不稳定、流量昂贵），本次改动不涉及下载链路。

## 已知取舍

- `PublishSingleFile=true` 需要联网还原 `Microsoft.NET.ILLink.Tasks`，
  故 C# 版仍采用 **framework-dependent 目录发布**：三个前端各约 0.5 MB，
  共用系统 .NET 8 运行时；换来体积远小于 Python 单文件 exe。
- exe 约 104 MB；二进制无法增量存储，每次重打包都会让 git 仓库永久增大约 100 MB，
  PyInstaller 内部已压缩（再套 deflate 只省 0.6%），所以只走 Release 附件、不进仓库。
- 163 解密内核按第三方客户端行为独立复现，**不属于**学无止仓库的 MIT 授权范围，
  本工具整体不声明 MIT。

## 许可与合规

- 运行时主链路独立编写，不含账号体系、加密服务或商业客户端代码，也不含任何账号凭据。
- 组件：.NET 8 / WPF（MIT）· PySide6（LGPL-3.0）· FFmpeg（LGPL-2.1+ / GPL，不随仓库分发）
  · 学无止（参考，MIT）；完整声明见仓库 `NOTICE.md` 第五节。
- 课程内容的权利不因本软件改变。请**只处理自己已购买、有权访问与保存的内容**，
  本工具不提供、也不鼓励用于未购内容的批量获取。
