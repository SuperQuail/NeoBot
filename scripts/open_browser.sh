#!/usr/bin/env bash
# 启动有头浏览器供手动登录认证
# 浏览器用户数据持久化在 data/browser/profiles/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${SCRIPT_DIR}/data/browser"
PROFILE_DIR="${DATA_DIR}/profiles/manual_login"
TARGET_URL="${1:-https://example.com}"

mkdir -p "${PROFILE_DIR}"

echo "启动浏览器: ${TARGET_URL}"
echo "用户数据目录: ${PROFILE_DIR}"
echo ""
echo "请在浏览器中完成登录后关闭窗口。"
echo "登录状态将保存在 ${PROFILE_DIR}，后续无头浏览器将复用此会话。"
echo ""

playwright open --profile-dir="${PROFILE_DIR}" "${TARGET_URL}"
