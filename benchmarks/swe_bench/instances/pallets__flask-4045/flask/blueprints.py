from __future__ import annotations


class Blueprint:
    def __init__(self, name: str, url_prefix: str = ""):
        self.name = name
        self.url_prefix = url_prefix
        self.rules: list[tuple[str, str]] = []

    def add_url_rule(self, rule: str, endpoint: str) -> None:
        """Register a URL rule on the blueprint.

        Bug: Does not handle trailing slash on url_prefix properly.
        """
        full_rule = f"{self.url_prefix}/{rule.lstrip('/')}"
        self.rules.append((full_rule, endpoint))
