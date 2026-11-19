# 兴趣岛视频下载器

把你自己账号里的**已购课程 / 体验营 / 公开课**归档到本地，支持断点续传、分片并发、
成品时长校验。只处理你有权访问的内容，请勿用于传播或商业分发。

## 下载

到 [Releases](https://github.com/chisenin/xqd-downloader/releases) 下载
`xqd-downloader-vX.Y.Z.exe` —— **单文件、自包含**：

- 不需要装 .NET 运行时（运行时已打进 exe 里）；
- 不需要装 Python、不需要解压成一堆 dll；
- Windows 10 / 11 x64，双击即用。

## 第一次运行

1. 顶栏「环境检查」→ 缺 ffmpeg 就点「一键安装 ffmpeg」（装到 `%USERPROFILE%\.xqd_tool\ffmpeg\bin`，
   不写系统 PATH、不需要管理员权限）。
2. 点「重新授权」→ 程序自动找 MuMu 并拉起装了兴趣岛的实例读取登录态。
   MuMu 装在非常规目录、或者只开了实例 2/3 都没关系：程序会按「运行中的进程 →
   开始菜单快捷方式 → 卸载注册表 → 各盘目录」找到它，并 **0~7 号实例全探**；
   实在定位不到会弹文件选择框让你选一次 `MuMuManager.exe`，位置记在
   `~/.xqd_tool/tools.json`，下次不再问。排障用 `--authcheck`。
3. 左侧勾选要下载的营 → 课表并入右侧表格 → 点「开始下载」。

## 换机器为什么现在能跑

旧版是「framework-dependent 目录 zip + 启动.bat」，还有一堆作者本机的硬编码路径。
v1.7.0 把这些全部拆掉了：

| 旧问题 | 现在 |
|---|---|
| 目标机器没有 .NET 8 桌面运行时 | 自包含单文件 exe，运行时打进去 |
| `D:\Program Files\Netease\MuMu` 写死 | 按盘符枚举 + 常见目录 + 可点选记住 |
| ffmpeg 写死在作者的本机目录 | 自装目录 → 点选记录 → 环境变量 → PATH |
| `adb.exe` / `192.168.1.101:5555` 写死 | adb 探测 + `adb devices` 取第一台在线设备 |
| `C:\Users\<作者名>\Downloads` 写死 | 读注册表里「下载」Known Folder（用户改到 D 盘也认） |

想手工指定也行，环境变量优先：

```
XQD_FFMPEG_DIR      ffmpeg/ffprobe 所在目录
XQD_MUMU_MANAGER    MuMuManager.exe 全路径
XQD_MUMU_HOME       MuMu 安装根目录
XQD_ADB             adb.exe 全路径
XQD_ADB_DEVICE      固定设备地址（如 127.0.0.1:16384）
XQD_COOKIE / QLD_COOKIE   直接给 cookie，跳过模拟器授权
```

## 仓库结构

```
xqd/                 Python 核心库（只做想法验证，零第三方依赖，不参与发版）
  config.py            配置与下载目录（注册表 Known Folder）
  probe.py             工具探测：ffmpeg / MuMu / adb / 在线设备
  naming.py            文件名规范（与 C# Naming.cs 一一对应）
  dedupe.py            已存在判定（主键 + 10KB + ffprobe 时长容差）
  mux.py               分片字节拼接 + ffmpeg -c copy 封装
  platform.py          兴趣岛业务网关（禁代理、认 state.code）
tools/probe_env.py   环境探测脚本（相当于 --check）
xqd-csharp/          C# 领域层：Xqd.Core / Xqd.Cli / Xqd.Server / Xqd.Tests
xqd-avalonia/        C# + Avalonia 正式 GUI（发版产物 = 这里打出来的单文件 exe）
docs/                已验证事实、API、踩坑记录、界面规格
```

## 自己构建

需要 .NET 8 SDK（Windows）。

```powershell
cd xqd-avalonia
.\build.cmd            # 输出 dist\xqd-downloader-v1.7.0.exe（自包含单文件）
.\build.cmd --check    # 命令行环境体检
```

Linux / Git Bash：

```bash
cd xqd-avalonia && ./build.sh
```

跑回归（281 项，离线，不发网络请求）：

```powershell
dotnet build xqd-csharp/Xqd.sln -c Release
.\xqd-csharp\src\Xqd.Tests\bin\Release\net8.0\Xqd.Tests.exe
```

## 命令行的那几个参数

```
xqd-downloader --version      打印版本
xqd-downloader --check        环境体检（依赖 / 目录 / 设备）
xqd-downloader --authcheck    授权诊断：MuMu 路径 + 各实例登录状态（换机器排障用）
xqd-downloader --install-deps 自动下载 ffmpeg 到 ~/.xqd_tool/ffmpeg/bin
```

## 发版

```bash
git tag v1.7.0 && git push origin master v1.7.0
```

GitHub Actions 会跑回归 → 构建单文件 exe → 核对文件版本与标签 → 创建 Release 并上传。
版本号唯一来源是 `xqd-avalonia/src/Xqd.Avalonia/Xqd.Avalonia.csproj` 里的 `<PkgVersion>`。

## 许可

见 [NOTICE.md](NOTICE.md)。仅供个人学习备份，请遵守平台条款与著作权法。
