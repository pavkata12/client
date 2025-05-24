@echo off
powershell -Command "Start-Process python -ArgumentList 'src/main.py' -Verb RunAs -WorkingDirectory '%~dp0'" 