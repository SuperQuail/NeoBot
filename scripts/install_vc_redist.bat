@echo off
chcp 65001 >nul
REM 一键安装 VC++ 2015-2022 运行库(联网下载,需管理员)
REM 解决 WinError 1114: onnxruntime / PyTorch DLL 初始化例程失败(运行库版本过旧)
echo ============================================================
echo  NeoBot - VC++ 运行库一键安装(联网下载)
echo  目标: 修复 onnxruntime / PyTorch 的 DLL 初始化失败(1114)
echo ============================================================
echo.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请以管理员身份运行本脚本(右键 - 以管理员身份运行)
    pause
    exit /b 1
)
set "URL=https://aka.ms/vs/17/release/vc_redist.x64.exe"
set "DOWNLOAD=%TEMP%\vc_redist.x64.exe"
echo [1/3] 在线下载 VC++ 运行库(约 25 MB)...
curl -L -o "%DOWNLOAD%" "%URL%"
if %errorlevel% neq 0 (
    echo [错误] 下载失败。请手动下载并以管理员身份运行:
    echo        %URL%
    pause
    exit /b 1
)
echo [2/3] 开始安装 VC++ 运行库(静默模式)...
"%DOWNLOAD%" /install /quiet /norestart
if %errorlevel% neq 0 (
    echo [错误] 安装失败,退出码 %errorlevel%
    echo        请手动下载并以管理员身份运行: %URL%
    pause
    exit /b 1
)
echo [3/3] 安装完成!请关闭并重新打开终端,然后运行:
echo         python scripts\onnx_deploy_check.py
echo         uv run neobot init
echo.
pause
