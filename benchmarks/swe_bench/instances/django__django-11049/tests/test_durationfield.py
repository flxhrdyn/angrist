from django.db.models.fields.duration import DurationField


def test_duration_format_error_message():
    field = DurationField()
    msg = field.get_error_message("invalid-val")
    assert "[DD] [[HH:]MM:]ss[.uuuuuu] format." in msg
    assert "[DD] [HH:[MM:]]ss[.uuuuuu] format." not in msg
