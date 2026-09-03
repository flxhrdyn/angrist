from __future__ import annotations


class Schema:
    def __init__(self, fields: dict[str, type]):
        self.fields = fields

    def _do_load(self, data: dict) -> dict:
        """Load and validate input dictionary against schema fields.

        Bug: Fails to convert string values to int for int fields.
        """
        result = {}
        for key in self.fields:
            if key not in data:

                continue
            val = data[key]
            # Bug: Does not cast int types, leaving str as str
            result[key] = val
        return result
