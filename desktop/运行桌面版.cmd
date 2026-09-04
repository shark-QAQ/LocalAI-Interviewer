@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist node_modules\electron\dist\electron.exe (
  echo 尚未安装 Electron，请先双击本文件夹的「安装桌面版.cmd」。
  pause
  exit /b 1
)
echo 正在启动桌面应用（首次运行会自动拉起后端与前端，请稍候）...
echo 关闭应用窗口即停止本应用拉起的服务。
call node_modules\.bin\electron.cmd .
pause
