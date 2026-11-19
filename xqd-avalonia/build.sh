#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  兴趣岛视频下载器 - Avalonia 版 构建脚本（Git Bash / MSYS）
#  用法：./build.sh            构建 Release（输出到 ./dist）
#        ./build.sh 1.7.1      指定版本号
#        ./build.sh check      跑无头环境体检
# ══════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")"

DOTNET=""
if [ -n "${DOTNET_ROOT:-}" ] && [ -x "$DOTNET_ROOT/dotnet" ]; then
    DOTNET="$DOTNET_ROOT/dotnet"
elif command -v dotnet >/dev/null 2>&1; then
    DOTNET="$(command -v dotnet)"
elif [ -x "/c/Program Files/dotnet/dotnet" ]; then
    DOTNET="/c/Program Files/dotnet/dotnet"
fi
if [ -z "$DOTNET" ]; then
    echo "[失败] 找不到 dotnet —— 请安装 .NET 8 SDK，或设置 DOTNET_ROOT 后重试。" >&2
    exit 1
fi

export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1

PROJ="src/Xqd.Avalonia/Xqd.Avalonia.csproj"
OUT="dist"
VER="${1:-1.7.0}"

if [ "${1:-}" = "check" ]; then
    "$DOTNET" run --project "$PROJ" -c Debug -- --check
    exit 0
fi

echo "[1/3] 还原依赖"
"$DOTNET" restore "$PROJ" --configfile "./NuGet.config" -r win-x64

echo "[2/3] 发布自包含单文件（win-x64，目标机器无需安装 .NET）"
"$DOTNET" publish "$PROJ" -c Release --no-restore -o "$OUT" -p:PkgVersion="$VER"

echo "[3/3] 产物"
ls -la "$OUT"
echo
echo "完成：$PWD/$OUT/xqd-downloader-v$VER.exe"
