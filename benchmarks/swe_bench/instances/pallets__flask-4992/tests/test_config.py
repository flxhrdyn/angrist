import json
from flask.config import Config


def test_from_file_json(tmp_path):
    p = tmp_path / "test.json"
    p.write_text(json.dumps({"KEY": "VALUE"}))
    c = Config(str(tmp_path))
    assert c.from_file("test.json", load=json.load)
    assert c["KEY"] == "VALUE"


def test_from_file_binary_mode(tmp_path):
    p = tmp_path / "test.bin"
    p.write_bytes(b"KEY=BINARY")

    def binary_loader(f):
        data = f.read()
        assert isinstance(data, bytes)
        k, v = data.decode().split("=")
        return {k: v}

    c = Config(str(tmp_path))
    assert c.from_file("test.bin", load=binary_loader, text=False)
    assert c["KEY"] == "BINARY"
