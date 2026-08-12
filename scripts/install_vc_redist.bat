@echo off
chcp 65001 >nul
REM 一键安装 VC++ 2015-2022 运行库(离线包,需管理员)
REM 解决 WinError 1114: onnxruntime / PyTorch DLL 初始化例程失败(运行库版本过旧)
echo ============================================================
echo  NeoBot - VC++ 运行库一键安装(离线包)
echo  目标: 修复 onnxruntime / PyTorch 的 DLL 初始化失败(1114)
echo ============================================================
echo.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请以管理员身份运行本脚本(右键 - 以管理员身份运行)
    pause
    exit /b 1
)
set "REDIST=%~dp0vc_redist\vc_redist.x64.exe"
if not exist "%REDIST%" (
    echo [错误] 未找到离线包: %REDIST%
    echo        请确认本脚本位于发布包的 scripts 目录内
    pause
    exit /b 1
)
echo [1/2] 开始安装 VC++ 运行库(静默模式)...
"%REDIST%" /install /quiet /norestart
if %errorlevel% neq 0 (
    echo [错误] 安装失败,退出码 %errorlevel%
    pause
    exit /b 1
)
echo [2/2] 安装完成!请关闭并重新打开终端,然后运行:
echo         python scripts\onnx_deploy_check.py
echo         uv run neobot init
echo.
pause
