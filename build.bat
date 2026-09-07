@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

if "%APP_VERSION%"=="" set APP_VERSION=1.0.0

echo ============================================================
echo   牙槽骨吸收测量 —— Windows 打包  v%APP_VERSION%
echo ------------------------------------------------------------
echo   产物 1: 单文件版 exe      发微信/U盘，双击即用，无需安装
echo   产物 2: 安装包 Setup.exe  正式安装，启动快 3 倍，带快捷方式
echo ============================================================
echo.

set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo [错误] 找不到 .venv，请先执行：
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

echo [1/6] 检查依赖冲突...
"%PY%" -c "import sys, json, subprocess; out = subprocess.run([sys.executable,'-m','pip','list','--format=json'],capture_output=True,text=True).stdout; pkgs = {p['name'].lower() for p in json.loads(out)}; sys.exit(2 if ('opencv-python' in pkgs and 'opencv-python-headless' in pkgs) else 0)"
if errorlevel 2 (
    echo.
    echo [错误] opencv-python 与 opencv-python-headless 同时存在。
    echo        前者自带一套 Qt，PyInstaller 会因两套 Qt binding 中止构建。
    echo        请执行： "%PY%" -m pip uninstall -y opencv-python
    exit /b 1
)

echo [2/6] 跑测试...
"%PY%" tests\test_core.py  || exit /b 1
"%PY%" tests\test_smoke.py || exit /b 1

echo.
echo [3/6] 安装 PyInstaller（若已安装则跳过）...
"%PY%" -m pip install --quiet --upgrade pyinstaller || exit /b 1

echo [4/6] 打单文件版（首次约 2-4 分钟）...
set BUILD_MODE=onefile
"%PY%" -m PyInstaller build.spec --noconfirm --clean || exit /b 1

echo [5/6] 打文件夹版（安装包用）...
set BUILD_MODE=onedir
"%PY%" -m PyInstaller build.spec --noconfirm || exit /b 1
set BUILD_MODE=

echo [6/6] 生成安装包...
set ISCC=
for %%P in (
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do if exist %%P set ISCC=%%P

if "%ISCC%"=="" (
    echo.
    echo [跳过] 没找到 Inno Setup，只产出了单文件版。
    echo        要生成安装包，先装 Inno Setup：
    echo            winget install --id JRSoftware.InnoSetup
    echo        然后重新运行 build.bat
) else (
    %ISCC% installer.iss || exit /b 1
)

echo.
echo ============================================================
echo   完成 —— 产物在 dist\
echo ============================================================
for %%F in ("dist\牙槽骨吸收测量.exe" "dist\牙槽骨吸收测量_安装包_v%APP_VERSION%.exe") do (
    if exist %%F (
        for %%A in (%%F) do (
            set /a MB=%%~zA/1048576
            echo   %%~nxA   !MB! MB
        )
    )
)
echo.
echo   给别人用：发「安装包」最好（启动快）；
echo             临时用/发微信：发「单文件版」，双击即用。
echo.
endlocal
