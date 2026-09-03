import re


class EncodingChecker:
    def __init__(self, notes: list[str]):
        self.notes = notes
        self._fixme_pattern: re.Pattern | None = None

    def open(self) -> None:
        """Compile fixme pattern from notes configuration."""
        notes = "|".join(re.escape(note) for note in self.notes)
        regex_string = rf"#\s*({notes})\b"
        self._fixme_pattern = re.compile(regex_string, re.IGNORECASE)

    def match_note(self, text: str) -> bool:
        if self._fixme_pattern is None:
            self.open()
        return bool(self._fixme_pattern.search(text))
