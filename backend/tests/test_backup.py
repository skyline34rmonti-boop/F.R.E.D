"""The backup tool uses only stdlib and supports a running SQLite WAL database."""
import importlib.util
from contextlib import closing
import os
from pathlib import Path
import sqlite3

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'backup.py'
spec = importlib.util.spec_from_file_location('fred_backup', SCRIPT)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def create_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE memories (content TEXT NOT NULL)')
        db.execute('INSERT INTO memories VALUES (?)', ('approved preference',))


def read_contents(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as db, db:
        return [row[0] for row in db.execute('SELECT content FROM memories')]


def test_online_backup_captures_committed_wal_and_restores(tmp_path):
    source = tmp_path / 'live.db'
    create_database(source)
    live = sqlite3.connect(source)
    try:
        live.execute('PRAGMA journal_mode=WAL')
        live.execute('INSERT INTO memories VALUES (?)', ('committed WAL memory',))
        live.commit()
        target = backup.copy_database(source, tmp_path / 'backup.db')
        assert read_contents(target) == ['approved preference', 'committed WAL memory']
        restored = backup.restore_database(target, tmp_path / 'restored.db', service_stopped=True)
        assert read_contents(restored) == read_contents(source)
    finally:
        live.close()
    if os.name != 'nt':
        assert target.stat().st_mode & 0o777 == 0o600
        assert restored.stat().st_mode & 0o777 == 0o600


def test_restore_requires_stopped_service_confirmation(tmp_path):
    source = tmp_path / 'source.db'
    create_database(source)
    destination = tmp_path / 'restore.db'
    with pytest.raises(backup.BackupError, match='Stop FRED'):
        backup.restore_database(source, destination)
    assert not destination.exists()


def test_existing_destination_is_never_overwritten(tmp_path):
    source, destination = tmp_path / 'source.db', tmp_path / 'saved.db'
    create_database(source)
    destination.write_bytes(b'precious existing backup')
    with pytest.raises(backup.BackupError, match='already exists'):
        backup.copy_database(source, destination)
    with pytest.raises(backup.BackupError, match='already exists'):
        backup.restore_database(source, destination, service_stopped=True)
    assert destination.read_bytes() == b'precious existing backup'


def test_corrupt_source_removes_only_incomplete_copy(tmp_path):
    source, destination = tmp_path / 'broken.db', tmp_path / 'backup.db'
    source.write_text('not a SQLite database')
    with pytest.raises(backup.BackupError, match='Database copy failed'):
        backup.copy_database(source, destination)
    assert source.read_text() == 'not a SQLite database'
    assert not destination.exists()


def test_missing_source_is_not_created(tmp_path):
    source = tmp_path / 'absent.db'
    with pytest.raises(backup.BackupError, match='Source database'):
        backup.copy_database(source, tmp_path / 'backup.db')
    assert not source.exists()


def test_nonexistent_parent_directory_is_rejected(tmp_path):
    source = tmp_path / 'source.db'
    create_database(source)
    with pytest.raises(backup.BackupError, match='parent directory'):
        backup.copy_database(source, tmp_path / 'absent' / 'backup.db')


def test_cli_exit_status_and_safe_messages(tmp_path, capsys):
    source = tmp_path / 'source.db'
    create_database(source)
    assert backup.main(['backup', str(source), str(tmp_path / 'backup.db')]) == 0
    assert 'integrity check passed' in capsys.readouterr().out
    assert backup.main(['restore', str(source), str(tmp_path / 'restore.db')]) == 1
    assert '--service-stopped' in capsys.readouterr().err


def test_timeout_removes_partial_destination(tmp_path, monkeypatch):
    source, destination = tmp_path / 'source.db', tmp_path / 'incomplete.db'
    create_database(source)
    times = iter([0.0, 2.0])
    monkeypatch.setattr(backup.time, 'monotonic', lambda: next(times))
    with pytest.raises(backup.BackupError, match='timed out'):
        backup.copy_database(source, destination, timeout=1)
    assert not destination.exists()
    assert read_contents(source) == ['approved preference']


def test_destination_symlink_is_not_followed(tmp_path):
    source = tmp_path / 'source.db'
    create_database(source)
    protected = tmp_path / 'protected.db'
    protected.write_bytes(b'existing protected content')
    destination = tmp_path / 'link.db'
    try:
        destination.symlink_to(protected)
    except OSError:
        pytest.skip('Creating symlinks is not permitted on this platform')
    with pytest.raises(backup.BackupError, match='already exists'):
        backup.copy_database(source, destination)
    assert protected.read_bytes() == b'existing protected content'
    assert destination.is_symlink()
