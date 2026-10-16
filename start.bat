@echo off
cd /d "%~dp0"
title EchoLab
echo Starting EchoLab (website and processing queue)...
python serve.py
if errorlevel 1 echo Startup failed. Check Python installation and dependencies.
pause
