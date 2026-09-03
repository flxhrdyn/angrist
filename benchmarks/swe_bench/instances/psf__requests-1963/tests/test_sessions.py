from requests.sessions import SessionRedirect


def test_redirect_303_converts_to_get():
    s = SessionRedirect()
    assert s.resolve_redirect_method(303, "POST") == "GET"


def test_redirect_307_308_preserves_post():
    s = SessionRedirect()
    assert s.resolve_redirect_method(307, "POST") == "POST"
    assert s.resolve_redirect_method(308, "PUT") == "PUT"
