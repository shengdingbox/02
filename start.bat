@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found! Please run setup first.
    pause
    exit /b 1
)

start "" venv\Scripts\pythonw.exe -m src.main
