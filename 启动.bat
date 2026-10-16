@echo off
cd /d "%~dp0"
title EchoLab
echo 正在启动 EchoLab(网页 + 自动解析队列)...
python serve.py
if errorlevel 1 echo.
if errorlevel 1 echo 启动失败。请确认已安装 Python,并且在这个目录打开。
pause
