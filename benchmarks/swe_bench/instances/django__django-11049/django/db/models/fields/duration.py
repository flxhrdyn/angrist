from typing import ClassVar


class DurationField:
    description = "Duration"
    default_error_messages: ClassVar[dict[str, str]] = {
        "invalid": "'%(value)s' value has an invalid format. It must be in [DD] [HH:[MM:]]ss[.uuuuuu] format."
    }

    def get_error_message(self, value: str) -> str:
        return self.default_error_messages["invalid"] % {"value": value}
