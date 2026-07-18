@echo off
chcp 65001 >nul 2>nul
echo ========================================
echo   Buddy Tool - 一键打包 EXE (Nuitka)
echo ========================================
echo.

cd /d "%~dp0"

:: 查找 Python 虚拟环境
set "PYEXE="
if exist ".venv\Scripts\python.exe" (
    set "PYEXE=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYEXE=venv\Scripts\python.exe"
) else (
    echo [ERROR] 未找到 Python 虚拟环境 (.venv 或 venv)
    echo 请先创建: python -m venv .venv
    pause
    exit /b 1
)

echo 使用 Python: %PYEXE%

:: 安装依赖（如果 requirements.txt 存在）
%PYEXE% -m pip install -r requirements.txt -q 2>nul

:: 安装 Nuitka（如果没有）
%PYEXE% -m pip show nuitka >nul 2>nul
if errorlevel 1 (
    echo 正在安装 Nuitka...
    %PYEXE% -m pip install nuitka -q
)

:: 清理旧构建
if exist "dist\BuddyTool" rmdir /s /q dist\BuddyTool
if exist "build" rmdir /s /q build
if exist "dist\BuddyTool.exe" del /q "dist\BuddyTool.exe"

echo 正在打包，请稍候（Nuitka 首次编译约 5-10 分钟）...
echo.

%PYEXE% -m nuitka ^
    --onefile ^
    --windows-console-mode=force ^
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
for %%A in ("dist\BuddyTool.exe") do echo 文件大小: %%~zA bytes

echo.
echo 将 dist\BuddyTool.exe 直接分发给用户即可
echo 用户双击运行，无需安装 Python
echo.

pause
