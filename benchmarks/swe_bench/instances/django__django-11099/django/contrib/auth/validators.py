import re


class RegexValidator:
    regex = ""
    message = "Enter a valid value."

    def __init__(self, regex=None, message=None):
        if regex is not None:
            self.regex = regex
        if message is not None:
            self.message = message
        self._compiled = re.compile(self.regex)

    def __call__(self, value: str) -> None:
        if not self._compiled.search(str(value)):
            raise ValueError(self.message)


class ASCIIUsernameValidator(RegexValidator):
    message = (
        "Enter a valid username. This value may contain only English letters, "
        "numbers, and @/./+/-/_ characters."
    )

    def __init__(self) -> None:
        super().__init__(
            regex=r"^[\w.@+-]+$",
            message=self.message,
        )
