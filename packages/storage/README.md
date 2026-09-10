# neobot-storage

SQLAlchemy 2.0 async storage layer for NeoBot. Implements the repository and unit-of-work ports defined in `neobot-contracts`.

## Usage

```python
from neobot_storage import create_engine, make_uow_factory

engine = create_engine("sqlite+aiosqlite:///neobot.db")
uow_factory = make_uow_factory(engine)

async with uow_factory() as uow:
    await uow.messages.save_message(msg)
    await uow.commit()
```

## Migrations

Migrations are run automatically on app startup via `run_migrations(db_url)` (absolute path
is injected, so no database file is created inside the source tree).

To run the Alembic CLI manually, always pass an **absolute** database path:

```bash
cd packages/storage/src/neobot_storage
alembic -x db_url=sqlite+aiosqlite:////absolute/path/to/neobot.db upgrade head
```

`alembic.ini` intentionally leaves `sqlalchemy.url` empty; a relative URL there would create a
stray empty `neobot.db` in the working directory (which must never be committed).
