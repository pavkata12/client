@echo off
powershell -Command "Start-Process cmd -ArgumentList '/c cd /d C:\Users\pavka\Desktop\client-main\client\src && python lock_screen_main.py' -Verb RunAs" 