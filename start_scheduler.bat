@echo off
rem Daypart Scheduler launcher (Windows 10)
rem Double-click this file. Uses the project-local venv; console stays open.
cd /d "%~dp0"
if not exist "%~dp0venv\Scripts\python.exe" (
    echo [ERROR] venv not found at "%~dp0venv".
    echo Expected a Python 3.12 venv with PySide6 installed.
    echo Recreate it with:  py -3.12 -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
call "%~dp0venv\Scripts\activate.bat"
python daypart_scheduler.py
echo.
echo Exit code: %ERRORLEVEL%
pause
