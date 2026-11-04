import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_database(url: str) -> tuple[Engine, sessionmaker]:
    parsed = make_url(url)
    if parsed.drivername.startswith('sqlite'):
        if parsed.database and parsed.database != ':memory:':
            database_path = Path(parsed.database).resolve()
            database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # New local databases contain private conversations and must not inherit
            # a world-readable process umask. Do not chmod arbitrary existing paths.
            try:
                descriptor = os.open(database_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
        options: dict = {'connect_args': {'check_same_thread': False}}
        if parsed.database == ':memory:':
            from sqlalchemy.pool import StaticPool
            options['poolclass'] = StaticPool
    else:
        options = {'pool_pre_ping': True}
    engine = create_engine(url, **options)
    if parsed.drivername.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def configure_sqlite(connection, _record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=5000')
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
