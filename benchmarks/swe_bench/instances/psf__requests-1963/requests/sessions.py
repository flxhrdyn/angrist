class SessionRedirect:
    def resolve_redirect_method(self, status_code: int, original_method: str) -> str:
        """Resolve redirect HTTP method based on status code."""
        # Bug: converts all redirects to GET regardless of 307/308
        if status_code in (301, 302, 303, 307, 308):
            return "GET"
        return original_method
