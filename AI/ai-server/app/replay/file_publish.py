"""Retry only Windows publication sharing/access failures, never data/provider operations."""
import os
import time

WINDOWS = os.name == 'nt'
WINDOWS_PUBLICATION_ERRORS = frozenset({5, 32, 33})
# Eight attempts, at most 1.95 seconds of waiting. Persistent failures propagate.
DELAYS = (0.05, 0.1, 0.2, 0.4, 0.4, 0.4, 0.4)


def _publish(operation, source, target):
    for attempt in range(len(DELAYS) + 1):
        try:
            operation(source, target)
            return
        except OSError as error:
            if not WINDOWS or getattr(error, 'winerror', None) not in WINDOWS_PUBLICATION_ERRORS or attempt == len(DELAYS):
                raise
            time.sleep(DELAYS[attempt])


def replace_file(source, target):
    """Replace atomically using the same already-written source on each attempt."""
    _publish(os.replace, source, target)


def publish_directory(source, target):
    """Publish a prepared directory; never remove or replace a competing output."""
    def rename(prepared, destination):
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('publication destination already exists')
        os.rename(prepared, destination)
    _publish(rename, source, target)
