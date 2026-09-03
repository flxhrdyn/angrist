import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pylint.checkers.misc import EncodingChecker


def test_standard_note_tag():
    checker = EncodingChecker(notes=["FIXME", "TODO"])
    checker.open()
    assert checker.match_note("# FIXME do something")


def test_punctuation_codetag_matches():
    checker = EncodingChecker(notes=["FIXME:", "???"])
    checker.open()
    assert checker.match_note("# FIXME: clean this up")
    assert checker.match_note("# ??? what is this")
