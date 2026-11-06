"""Bounded Windows file-replacement retries; never retries a provider request."""
import os

from .dataset import canonical
from .file_publish import replace_file


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    replace_file(temporary, path)
