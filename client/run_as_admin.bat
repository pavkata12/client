@echo off
set "WORKDIR=C:\Users\pavka\OneDrive\Desktop\client-main\client\src"
set "PYFILE=lock_screen_main.py"

REM Check if the working directory exists
if not exist "%WORKDIR%" (
    echo ERROR: Working directory "%WORKDIR%" does not exist.
    pause
    exit /b 1
)

REM Run the Python script as admin, in the background, with no console window
powershell -WindowStyle Hidden -Command "Start-Process pythonw -ArgumentList '%PYFILE%' -WorkingDirectory '%WORKDIR%' -Verb RunAs" 