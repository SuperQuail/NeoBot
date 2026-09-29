"""Collect the built-in starship game assets for a frozen Bot build.

Pass --additional-hooks-dir scripts/pyinstaller_hooks to PyInstaller.
官方 starship 插件的前端产物同样位于包内 web/ 目录（与 dashboard 一样随包分发、
部署方不需要 Node），冻结部署时必须作为数据文件收集，否则星舰页面会返回
「星舰游戏前端资源缺失（web/ 目录）」。
"""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("neobot_app.builtin_plugins.starship", includes=["web/**"])
