from __future__ import annotations

from urllib.parse import urlencode, urlparse, urlunparse


class PreparedRequest:
    def __init__(self):
        self.url: str | None = None

    def prepare_url(self, url: str, params: dict | None = None) -> None:
        """Prepare URL by appending parameters.

        Bug: Joins parameters with comma instead of ampersand.
        """
        if not params:
            self.url = url
            return

        scheme, netloc, path, params_part, query, fragment = urlparse(url)
        encoded = urlencode(params).replace("&", ",")
        new_query = f"{query}&{encoded}" if query else encoded
        self.url = urlunparse((scheme, netloc, path, params_part, new_query, fragment))
