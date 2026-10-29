import json
import os
from pathlib import Path
from .platform_windows import protect


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def read(self, name, default=None):
        path = self.path / (name + ".bin")
        if not path.exists():
            return default
        # Never silently overwrite unreadable encrypted data with defaults.
        return protect(path.read_bytes(), decrypt=True)

    def write(self, name, content):
        path = self.path / (name + ".bin")
        temp = path.with_suffix(".tmp")
        temp.write_bytes(protect(content))
        os.replace(temp, path)

    def load(self, name, default):
        data = self.read(name)
        return default if data is None else json.loads(data)

    def save(self, name, obj):
        self.write(name, json.dumps(obj).encode("utf-8"))
