@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在检查服务并打开独立应用窗口...
python open_app.py
echo.
pause
