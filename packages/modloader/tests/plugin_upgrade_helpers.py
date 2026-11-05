"""构造带真实 SQLite 和版本迁移的历史插件包。"""

from pathlib import Path

from neobot_modloader.sdk.tooling import build_package, export_contract


def project(root: Path, version: int, *, migration_failure: bool = False, startup_failure: bool = False) -> Path:
    source = root / "tasks"
    source.mkdir(parents=True)
    field = "caption" if version == 1 else "board_title"
    column = "text" if version == 1 else "title"
    (source / "plugin.toml").write_text(
        f'name = "tasks"\nversion = "0.{version}.0"\n'
        '[sdk]\nversion = 1\ncontract = "plugin.contract.json"\n'
        f"[sdk.storage]\nconfig_version = {version}\ndata_version = {version}\n",
        encoding="utf-8",
    )
    (source / "__init__.py").write_text(
        "from contextlib import closing\nimport sqlite3\n"
        "from pydantic import BaseModel\nfrom neobot_modloader import Plugin\n"
        f'class Config(BaseModel):\n    {field}: str = "默认标题"\n'
        f'plugin = Plugin("tasks", version="0.{version}.0", config=Config)\n'
        "@plugin.on_load\nasync def load(ctx):\n"
        "    ctx.data_dir.mkdir(parents=True, exist_ok=True)\n"
        '    with closing(sqlite3.connect(ctx.data_dir / "tasks.sqlite3")) as db, db:\n'
        f'        db.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, {column} TEXT NOT NULL)")\n'
        f'        db.execute("SELECT {column} FROM tasks").fetchall()\n'
        + (
            "@plugin.on_startup\nasync def fail(ctx):\n"
            '    with closing(sqlite3.connect(ctx.data_dir / "tasks.sqlite3")) as db, db:\n'
            "        db.execute(\"INSERT INTO tasks(title) VALUES ('候选代写入')\")\n"
            '    raise RuntimeError("合成启动失败")\n'
            if startup_failure
            else ""
        ),
        encoding="utf-8",
    )
    if version == 2:
        migrations = source / "migrations"
        migrations.mkdir()
        with (source / "plugin.toml").open("a", encoding="utf-8") as manifest:
            for kind in ("config", "data"):
                manifest.write(
                    f'\n[[sdk.migrations]]\nkind = "{kind}"\nfrom = 1\nto = 2\nentry = "migrations/{kind}.py"\n'
                )
        (migrations / "config.py").write_text(
            "def migrate(ctx):\n    path = ctx.config_path\n"
            '    path.write_text(path.read_text(encoding="utf-8").replace("caption", "board_title"), encoding="utf-8")\n',
            encoding="utf-8",
        )
        (migrations / "data.py").write_text(
            "from contextlib import closing\nimport sqlite3\n"
            "def migrate(ctx):\n"
            '    with closing(sqlite3.connect(ctx.data_dir / "tasks.sqlite3")) as db, db:\n'
            '        db.execute("ALTER TABLE tasks RENAME COLUMN text TO title")\n'
            + ('    raise RuntimeError("合成迁移失败")\n' if migration_failure else ""),
            encoding="utf-8",
        )
    exported = export_contract(source)
    assert exported.ok, exported.errors
    return source


def package(source: Path, target: Path) -> Path:
    result = build_package(source, target)
    assert result.ok, result.errors
    return target
