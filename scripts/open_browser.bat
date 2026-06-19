@echo off
REM 启动有头浏览器供手动登录认证
REM 浏览器用户数据持久化在 data/browser/profiles/

set SCRIPT_DIR=%~dp0..
set DATA_DIR=%SCRIPT_DIR%\data\browser
set PROFILE_DIR=%DATA_DIR%\profiles\manual_login
set TARGET_URL=%1
if "%TARGET_URL%"=="" set TARGET_URL=https://example.com

if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"

echo 启动浏览器: %TARGET_URL%
echo 用户数据目录: %PROFILE_DIR%
echo.
echo 请在浏览器中完成登录后关闭窗口。
echo 登录状态将保存在 %PROFILE_DIR%，后续无头浏览器将复用此会话。
echo.

playwright open --profile-dir="%PROFILE_DIR%" "%TARGET_URL%"
