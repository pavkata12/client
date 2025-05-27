@echo off
powershell -Command "Start-Process python -ArgumentList 'src/lock_screen_main.py' -WindowStyle Hidden -Verb RunAs" 