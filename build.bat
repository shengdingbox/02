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
    --standalone ^
    --windows-console-mode=disable ^
    --enable-plugin=pyside6 ^
    --include-data-dir=assets=assets ^
    --include-data-dir=src\i18n=src\i18n ^
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
echo   输出目录: dist\app.dist\
echo   EXE 文件: dist\app.dist\BuddyTool.exe
echo ========================================
echo.

:: 显示目录大小
for /f %%A in ('dir /s "dist\app.dist" ^| findstr /c:"File(s)"') do echo %%A

echo.
echo 可以将 dist\app.dist 整个目录打包成 zip 分发给用户
echo 用户双击 BuddyTool.exe 即可运行，无需安装 Python
echo.

:: 询问是否压缩成 zip
set /p ZIP="是否压缩成 zip? (y/n): "
if /i "%ZIP%"=="y" (
    echo 正在压缩...
    venv\Scripts\python.exe -c "import zipfile,os;z=zipfile.ZipFile('dist/BuddyTool.zip','w',zipfile.ZIP_DEFLATED);[z.write(os.path.join(r,f),os.path.join('BuddyTool',os.path.relpath(os.path.join(r,f),'dist/app.dist'))) for r,d,fs in os.walk('dist/app.dist') for f in fs];z.close();print('✅ 压缩完成: dist/BuddyTool.zip')"
)

pause
