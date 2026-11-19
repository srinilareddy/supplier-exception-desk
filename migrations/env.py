from alembic import context
from sqlalchemy import create_engine, pool

from desk import models  # noqa: F401
from desk.config import Settings
from desk.db import Base

database_url = Settings().database_url.get_secret_value()

if context.is_offline_mode():
    context.configure(
        url=database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
