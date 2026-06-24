@echo off
chcp 65001 >nul 2>nul
echo ========================================
echo   Antigravity Tools - 打包更新
echo ========================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found!
    pause
    exit /b 1
)

:: 读取当前版本号
set /p VERSION=<src\VERSION
echo 当前版本: v%VERSION%
echo.

:: 设置新版本号
set /p NEW_VER="输入新版本号 (直接回车保持 %VERSION%): "
if "%NEW_VER%"=="" set NEW_VER=%VERSION%

:: 写入新版本号
echo %NEW_VER%> src\VERSION
echo 版本号已更新为: v%NEW_VER%

:: 生成更新包 (只打包 src/ 和 VERSION)
echo.
echo 正在打包...
if exist "update.zip" del "update.zip"

:: 使用 Python 打包 (避免 Windows tar 路径问题)
venv\Scripts\python.exe -c "import zipfile, os; z = zipfile.ZipFile('update.zip', 'w', zipfile.ZIP_DEFLATED); [z.write(os.path.join(r,f), os.path.join(r,f)) for r, ds, fs in os.walk('src') for f in fs]; z.write('src/VERSION', 'VERSION'); z.close()"
if errorlevel 1 (
    echo [ERROR] 打包失败!
    pause
    exit /b 1
)

:: 计算 SHA256
echo.
echo 计算 SHA256...
for /f "tokens=*" %%h in ('venv\Scripts\python.exe -c "import hashlib; f=open('update.zip','rb'); h=hashlib.sha256(f.read()).hexdigest(); f.close(); print(h)"') do set SHA256=%%h

echo SHA256: %SHA256%
echo.

:: 生成 version.json
echo 生成 version.json...
(
echo {
echo     "version": "%NEW_VER%",
echo     "changelog": "版本更新",
echo     "release_date": "%date:~0,4%-%date:~5,2%-%date:~8,2%",
echo     "download_url": "http://103.36.63.44:9680/update.zip",
echo     "sha256": "%SHA256%"
}
) > version.json

echo.
echo ========================================
echo   打包完成!
echo   版本: v%NEW_VER%
echo   文件: update.zip
echo   SHA256: %SHA256%
echo ========================================
echo.
echo 请将 update.zip 和 version.json 上传到服务器:
echo   scp update.zip root@103.36.63.44:/var/www/html/antigravity-tools/
echo   scp version.json root@103.36.63.44:/var/www/html/antigravity-tools/
echo.

:: 询问是否自动上传
set /p UPLOAD="是否自动上传到服务器? (y/n): "
if /i "%UPLOAD%"=="y" (
    echo.
    echo 上传 update.zip...
    scp update.zip root@103.36.63.44:/var/www/html/antigravity-tools/
    echo 上传 version.json...
    scp version.json root@103.36.63.44:/var/www/html/antigravity-tools/
    echo.
    echo ✅ 上传完成!
)

pause
