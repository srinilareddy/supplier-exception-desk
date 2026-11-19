from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from desk.config import Settings


class Base(DeclarativeBase):
    pass


def make_session_factory(settings: Settings) -> sessionmaker:
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )
    return sessionmaker(engine, expire_on_commit=False)
