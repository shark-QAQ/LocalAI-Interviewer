@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在把 Electron 安装到本文件夹的 node_modules（下载缓存也放项目内）...
echo 依赖较大（约 100MB+），请耐心等待；删除整个项目文件夹即可彻底清理。
echo.
set ELECTRON_CACHE=%~dp0.electron-cache
set electron_config_cache=%~dp0.electron-cache
set npm_config_cache=%~dp0.npm-cache
rem 国内网络下 GitHub 直连不稳，走 npmmirror 的 Electron 二进制镜像（可自行改回官方）
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
call npm install
rem 新版 npm 默认拦安装脚本，electron 二进制可能没自动下载；缺了就手动补拉
if not exist node_modules\electron\dist\electron.exe (
  echo Electron 二进制未自动下载，正在手动补拉…
  cd node_modules\electron
  call node install.js
  cd ..\..
)
echo.
echo 安装完成。双击本文件夹的「运行桌面版.cmd」或桌面快捷方式即可启动。
pause
