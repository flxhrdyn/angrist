from sphinx.ext.autodoc.options import inherited_members_option


def test_inherited_members_default():
    assert inherited_members_option(True) == {"object"}
    assert inherited_members_option(None) == {"object"}


def test_inherited_members_multiple_classes():
    res = inherited_members_option("Base1, Base2, Base3")
    assert res == {"Base1", "Base2", "Base3"}
