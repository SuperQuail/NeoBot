"""Collect the built-in stdio Python LSP worker for an existing Bot build.

Pass ``--additional-hooks-dir scripts/pyinstaller_hooks`` to PyInstaller. Keep
the CLI early worker dispatch and build with console/stdio support (not
``--windowed``). The wheel publish script is unrelated to frozen deployment.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# pylsp discovers plugins through installed distribution entry points, not
# normal imports. Jedi typeshed stubs and Parso grammars must remain real files.
# Hover docstring converters use a second dynamic entry-point group.
hiddenimports = collect_submodules("pylsp") + collect_submodules("docstring_to_markdown")
datas = copy_metadata("python-lsp-server", recursive=True)
for package in ("pylsp", "jedi", "parso"):
    datas += collect_data_files(package)
