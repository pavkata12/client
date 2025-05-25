@echo off
set SCRIPT_PATH=%~dp0src\lock_screen_main.py
set PYTHON_PATH=%~dp0..\venv\Scripts\python.exe

powershell -Command "Start-Process '%PYTHON_PATH%' -ArgumentList '%SCRIPT_PATH%' -Verb RunAs -WorkingDirectory '%~dp0src'" 