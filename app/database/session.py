import logging
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.database.migrations import migrate

log = logging.getLogger("fashion_ai.database")


def create_database(url: str) -> sessionmaker:
    database = make_url(url).database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def sqlite_options(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    migrate(engine)
    log.info("database_initialized")
    return sessionmaker(engine, expire_on_commit=False)
