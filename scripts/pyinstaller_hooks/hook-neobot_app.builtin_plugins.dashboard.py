"""Collect the built-in dashboard panel assets for a frozen Bot build.

Pass --additional-hooks-dir scripts/pyinstaller_hooks to PyInstaller.
官方 dashboard 插件的前端产物位于包内 web/ 目录，冻结部署时必须作为数据文件
收集，否则面板会返回「前端资源缺失」。
"""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("neobot_app.builtin_plugins.dashboard", includes=["web/**"])
