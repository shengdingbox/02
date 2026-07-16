@echo off
chcp 65001 >nul 2>nul
echo ========================================
echo   Buddy Tool - 一键打包 EXE (Nuitka)
echo ========================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found!
    pause
    exit /b 1
)

:: 安装 Nuitka（如果没有）
venv\Scripts\pip.exe show nuitka >nul 2>nul
if errorlevel 1 (
    echo 正在安装 Nuitka...
    venv\Scripts\pip.exe install nuitka -q
)

:: 清理旧构建
if exist "dist\BuddyTool" rmdir /s /q dist\BuddyTool
if exist "build" rmdir /s /q build

echo 正在打包，请稍候（Nuitka 首次编译约 5-10 分钟）...
echo.

venv\Scripts\python.exe -m nuitka ^
    --onefile ^
    --windows-console-mode=disable ^
    --enable-plugin=pyside6 ^
    --include-data-dir=assets=assets ^
    --include-data-dir=src\i18n=src\i18n ^
    --include-data-file=src\VERSION=src\VERSION ^
    --output-dir=dist ^
    --output-filename="BuddyTool.exe" ^
    --assume-yes-for-downloads ^
    app.py

if errorlevel 1 (
    echo.
    echo [ERROR] 打包失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo   ✅ 打包成功！
echo   输出文件: dist\BuddyTool.exe
echo ========================================
echo.

:: 显示文件大小
for /f %%A in ('dir /b "dist\BuddyTool.exe"') do echo 文件: %%A

echo.
echo 将 dist\BuddyTool.exe 直接分发给用户即可
echo 用户双击运行，无需安装 Python
echo.

pause
