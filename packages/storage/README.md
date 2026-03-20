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

```bash
cd packages/storage
alembic upgrade head
```
