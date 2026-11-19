@echo off
rem ================================================================
rem  XQD Downloader - Avalonia edition build script
rem  Usage: build.cmd            build Release into .\dist
rem         build.cmd 1.7.1      use a specific version
rem         build.cmd --check    run the headless environment check
rem  NOTE: this file must stay CRLF + ASCII, otherwise cmd.exe mis-parses it.
rem ================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "DOTNET="
if defined DOTNET_ROOT if exist "%DOTNET_ROOT%\dotnet.exe" set "DOTNET=%DOTNET_ROOT%\dotnet.exe"
if not defined DOTNET (
    for /f "delims=" %%i in ('where dotnet 2^>nul') do if not defined DOTNET set "DOTNET=%%i"
)
if not defined DOTNET if exist "%ProgramFiles%\dotnet\dotnet.exe" set "DOTNET=%ProgramFiles%\dotnet\dotnet.exe"
if not defined DOTNET (
    echo [FAIL] dotnet not found - install the .NET 8 SDK, or set DOTNET_ROOT and retry.
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

echo [1/3] restore
"%DOTNET%" restore "%PROJ%" --configfile ".\NuGet.config" -r win-x64 || exit /b 1

echo [2/3] publish self-contained single file (win-x64, no .NET needed on target)
"%DOTNET%" publish "%PROJ%" -c Release --no-restore -o "%OUT%" -p:PkgVersion=%VER% -p:DebugType=None || exit /b 1

echo [3/3] artifact
dir /b "%OUT%"
echo.
echo done: %CD%\%OUT%\xqd-downloader-v%VER%.exe
