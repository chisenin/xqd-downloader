@echo off
rem ══════════════════════════════════════════════════════════════
rem  兴趣岛视频下载器 - Avalonia 版 构建脚本
rem  用法：build.cmd            构建 Release（输出到 .\dist）
rem        build.cmd 1.7.1      指定版本号
rem        build.cmd --check    跑无头环境体检
rem ══════════════════════════════════════════════════════════════
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "DOTNET="
if defined DOTNET_ROOT if exist "%DOTNET_ROOT%\dotnet.exe" set "DOTNET=%DOTNET_ROOT%\dotnet.exe"
if not defined DOTNET (
    for /f "delims=" %%i in ('where dotnet 2^>nul') do if not defined DOTNET set "DOTNET=%%i"
)
if not defined DOTNET if exist "%ProgramFiles%\dotnet\dotnet.exe" set "DOTNET=%ProgramFiles%\dotnet\dotnet.exe"
if not defined DOTNET (
    echo [失败] 找不到 dotnet —— 请安装 .NET 8 SDK，或设置 DOTNET_ROOT 后重试。
    exit /b 1
)

set "PROJ=src\Xqd.Avalonia\Xqd.Avalonia.csproj"
set "OUT=dist"
set "VER=1.7.1"
if not "%~1"=="" if not "%~1"=="--check" set "VER=%~1"

if "%~1"=="--check" (
    "%DOTNET%" run --project "%PROJ%" -c Debug -- --check
    exit /b %errorlevel%
)

echo [1/3] 还原依赖
"%DOTNET%" restore "%PROJ%" --configfile ".\NuGet.config" -r win-x64 || exit /b 1

echo [2/3] 发布自包含单文件（win-x64，目标机器无需安装 .NET）
"%DOTNET%" publish "%PROJ%" -c Release --no-restore -o "%OUT%" -p:PkgVersion=%VER% -p:DebugType=None || exit /b 1

echo [3/3] 产物
dir /b "%OUT%"
echo.
echo 完成：%CD%\%OUT%\xqd-downloader-v%VER%.exe
