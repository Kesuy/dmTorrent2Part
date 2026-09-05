from dmtorrent2part.bencode import decode, encode


def test_roundtrip():
    value = {b"a": 1, b"b": [b"x", 2], b"c": {b"z": b"ok"}}
    assert decode(encode(value)) == value
