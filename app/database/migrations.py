"""Versioned additive schema migration, with a SQLite-consistent pre-upgrade backup."""
import logging
import sqlite3
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine

from app.database.models import Base
from app.database.m1_models import SchemaMigration

log = logging.getLogger("fashion_ai.migrations")


def migrate(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    if "schema_migrations" in tables:
        with engine.connect() as connection:
            if connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == 1)):
                return
    database = engine.url.database
    if "projects" in tables and database and database != ":memory:":
        path = Path(database)
        backup = path.with_name(f"{path.stem}.pre-m1-{uuid4().hex[:8]}.db")
        with sqlite3.connect(str(path)) as source, sqlite3.connect(str(backup)) as destination:
            source.backup(destination)
        log.info("m0_database_backup_created")
    with engine.connect() as connection:
        # Force a real SQLite DDL transaction (pysqlite otherwise defers BEGIN).
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            Base.metadata.create_all(connection)
            if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == 1)):
                connection.execute(SchemaMigration.__table__.insert().values(version=1))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    log.info("schema_migration_completed version=1")
