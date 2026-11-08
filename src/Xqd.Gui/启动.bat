@echo off
setlocal EnableDelayedExpansion
title 兴趣岛视频下载器 · 启动

rem ============================================================
rem  ★ 兴趣岛视频下载器 —— 启动引导脚本
rem
rem  这个脚本存在的原因：
rem    本工具是 framework-dependent 发布（**刻意不打包 .NET 运行时**，
rem    免得压缩包变成 160MB），所以别人的电脑若没装
rem    「.NET 8 桌面运行时」，双击 exe 会直接报错或闪退 —— 那种情况
rem    程序自己没法自检（它压根没起来）。
rem
rem  这个脚本用 Windows 自带的 cmd 写成（不需要任何运行时），
rem  负责：检测 .NET → 没有就给出下载链接 → 装好后自动启动 GUI。
rem
rem  ★ 正常情况下你**不需要用它** —— 直接双击
rem    xqd-downloader-vX.Y.Z.exe 就行。这个脚本只是给
rem    「双击没反应」的人准备的一条稳妥路径。
rem ============================================================

cd /d "%~dp0"

rem ── 找到同目录的 GUI 可执行文件（名字带版本号）────────────
set "GUIEXE="
for %%F in (xqd-downloader-v*.exe) do (
    if not "%%~nxF"=="%~nx0" set "GUIEXE=%%~nxF"
)
if not defined GUIEXE (
    echo.
    echo   [x] 找不到主程序 xqd-downloader-v*.exe
    echo.
    echo       本脚本必须和主程序放在同一个目录里。
    echo       当前目录：%CD%
    echo.
    pause
    exit /b 1
)

rem ── 检测 .NET 8 桌面运行时 ────────────────────────────────
rem    判据：dotnet --list-runtimes 里有 "Microsoft.WindowsDesktop.App 8.x"
rem    —— 只有 Microsoft.NETCore.App 是不够的，WPF 要的是**桌面**运行时。
rem    dotnet.exe 可能不在 PATH（装过但没配环境变量），所以也查默认安装位置。
set "HAS_DOTNET="
set "DOTNET_EXE=dotnet"
where dotnet >nul 2>&1 || set "DOTNET_EXE="
if not defined DOTNET_EXE if exist "%ProgramFiles%\dotnet\dotnet.exe" set "DOTNET_EXE=%ProgramFiles%\dotnet\dotnet.exe"
if not defined DOTNET_EXE if exist "%ProgramFiles(x86)%\dotnet\dotnet.exe" set "DOTNET_EXE=%ProgramFiles(x86)%\dotnet\dotnet.exe"

if defined DOTNET_EXE (
    for /f "delims=" %%R in ('"%DOTNET_EXE%" --list-runtimes 2^>nul') do (
        echo %%R | findstr /C:"Microsoft.WindowsDesktop.App 8." >nul && set "HAS_DOTNET=1"
    )
)

if defined HAS_DOTNET goto :launch

rem ── 缺运行时：引导下载 ────────────────────────────────────
cls
echo.
echo   ============================================================
echo     缺少 .NET 8 桌面运行时
echo   ============================================================
echo.
echo   这个工具是 WPF 程序，需要 Microsoft's .NET 8 桌面运行时。
echo   你的电脑上没装，所以双击主程序会报错或闪退。
echo.
echo   安装方法（两步，约 1 分钟）：
echo.
echo     1) 点下面的链接下载安装包（约 55 MB）：
echo        https://dotnet.microsoft.com/download/dotnet/8.0
echo.
echo        国内网络若打不开，可用这个微软官方直链：
echo        https://builds.dotnet.microsoft.com/dotnet/WindowsDesktop/8.0.22/windowsdesktop-runtime-8.0.22-win-x64.exe
echo.
echo     2) 双击下载好的 windowsdesktop-runtime-*.exe，一路点「下一步」
echo        装完后再双击本脚本即可。
echo.
echo   ------------------------------------------------------------
echo.

rem 尝试直接打开官方下载页（打不开也不影响手动复制上面的链接）
start "" "https://dotnet.microsoft.com/download/dotnet/8.0" 2>nul

echo   已尝试打开下载页面。若没弹出浏览器，请手动复制上面的链接。
echo.
echo   ★ 装好运行时后，重新双击这个脚本即可启动。
echo.
pause
exit /b 1

rem ── 有运行时：启动 GUI ────────────────────────────────────
:launch
echo   正在启动 %GUIEXE% ...
start "" "%GUIEXE%"
exit /b 0
