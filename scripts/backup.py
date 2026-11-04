"""Portable, non-overwriting SQLite backup/restore for FRED.

Uses SQLite's online backup API, including committed WAL transactions. Credentials
are deliberately excluded. Stop FRED before restoring and select a new database
path; this utility never overwrites an existing destination.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import time


class BackupError(Exception):
    """A backup could not be completed safely."""


def copy_database(source: Path, destination: Path, *, timeout: float = 30) -> Path:
    """Copy a consistent snapshot into a new private file and check integrity.

    Parent directories must exist. Any incomplete destination created by this
    operation is removed on failure; pre-existing files are never replaced.
    """
    if timeout <= 0:
        raise BackupError('Timeout must be positive.')
    source = Path(source).expanduser()
    destination = Path(destination).expanduser()
    if destination.is_symlink() or destination.exists():
        raise BackupError('Destination already exists; choose a new file.')
    try:
        source = source.resolve(strict=True)
    except OSError as exc:
        raise BackupError('Source database does not exist or is inaccessible.') from exc
    if not source.is_file():
        raise BackupError('Source must be a SQLite database file.')
    destination = destination.absolute()
    if not destination.parent.is_dir():
        raise BackupError('Destination parent directory must already exist.')
    if source == destination.resolve():
        raise BackupError('Source and destination must be different files.')
    created = False
    deadline = time.monotonic() + timeout

    def check_timeout(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise BackupError('Backup timed out; retry when the database is less busy.')

    try:
        # Exclusive creation also protects against a destination appearing after
        # the check above. Mode 0600 applies on POSIX; use private ACLs on Windows.
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        created = True
        # sqlite3's own context manager does not close connections. Explicit
        # closure is required before failure cleanup on Windows.
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as original:
            with closing(sqlite3.connect(destination, timeout=5)) as copied:
                original.backup(copied, pages=256, progress=check_timeout, sleep=0.1)
                result = [row[0] for row in copied.execute('PRAGMA integrity_check')]
                if result != ['ok']:
                    raise BackupError('Copied database failed SQLite integrity validation.')
    except BaseException as exc:
        # Interrupting a large copy must not leave a plausible-looking backup.
        # Re-raise cancellation/system exceptions after removing our output.
        if created:
            destination.unlink(missing_ok=True)
        if isinstance(exc, (BackupError, KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(exc, (OSError, sqlite3.Error)):
            raise BackupError('Database copy failed; verify file access and SQLite integrity.') from exc
        raise
    return destination


def restore_database(source: Path, destination: Path, *, service_stopped: bool = False) -> Path:
    if not service_stopped:
        raise BackupError('Stop FRED before restore and confirm with --service-stopped.')
    return copy_database(source, destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('backup', 'restore'):
        command = commands.add_parser(name)
        command.add_argument('source', type=Path)
        command.add_argument('destination', type=Path, help='New destination file; never overwritten.')
        if name == 'restore':
            command.add_argument('--service-stopped', action='store_true',
                                 help='Confirm the FRED service has been stopped.')
    args = parser.parse_args(argv)
    try:
        if args.command == 'restore':
            restore_database(args.source, args.destination, service_stopped=args.service_stopped)
        else:
            copy_database(args.source, args.destination)
    except BackupError as exc:
        print(f'FRED {args.command} failed: {exc}', file=sys.stderr)
        return 1
    print(f'FRED {args.command} complete; SQLite integrity check passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
