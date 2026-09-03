from __future__ import annotations

import os
import typing as t


class Config(dict):
    def __init__(self, root_path: str = "."):
        super().__init__()
        self.root_path = root_path

    def from_file(
        self,
        filename: str,
        load: t.Callable[[t.IO[t.Any]], t.Mapping[str, t.Any]],
        silent: bool = False,
    ) -> bool:
        """Update the values in the config from a file that is loaded using the load parameter."""
        filepath = os.path.join(self.root_path, filename)
        try:
            with open(filepath) as f:
                obj = load(f)
        except OSError:
            if silent:
                return False
            raise
        self.update(obj)
        return True
