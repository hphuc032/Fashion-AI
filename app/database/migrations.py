"""Versioned additive schema migration, with a SQLite-consistent pre-upgrade backup."""
import logging
import importlib
import pkgutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine

from app.database.models import Base
from app.database.m1_models import SchemaMigration

log = logging.getLogger("fashion_ai.migrations")


def migrate(engine: Engine) -> None:
    # Local schema plugins allow independent additive feature migrations.
    for module in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if module.name.endswith("_schema"):
            importlib.import_module(f"app.database.{module.name}")
    tables = set(inspect(engine).get_table_names())
    applied = set()
    if "schema_migrations" in tables:
        with engine.connect() as connection:
            applied = set(connection.scalars(select(SchemaMigration.version)))
    required = {1} | {int(table.info.get("schema_version", 1)) for table in Base.metadata.tables.values()}
    if required.issubset(applied):
        return
    database = engine.url.database
    if "projects" in tables and database and database != ":memory:":
        path = Path(database)
        label = "m1" if 1 not in applied else f"v{max(required)}"
        backup = path.with_name(f"{path.stem}.pre-{label}-{uuid4().hex[:8]}.db")
        with sqlite3.connect(str(path)) as source, sqlite3.connect(str(backup)) as destination:
            source.backup(destination)
        log.info("m0_database_backup_created")
    with engine.connect() as connection:
        # Force a real SQLite DDL transaction (pysqlite otherwise defers BEGIN).
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            Base.metadata.create_all(connection)
            existing = set(connection.scalars(select(SchemaMigration.version)))
            for version in sorted(required - existing):
                connection.execute(SchemaMigration.__table__.insert().values(version=version))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    log.info("schema_migration_completed version=1")
