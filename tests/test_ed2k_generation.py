from dmtorrent2part.ed2k import hash_file, md4


def test_md4_vectors():
    assert md4(b"").hex() == "31d6cfe0d16ae931b73c59d7e0c089c0"
    assert md4(b"a").hex() == "bde52cb31de33e46245e05fbdbd6fb24"
    assert md4(b"abc").hex() == "a448017aaf21d8525fc10ae87aa6729d"


def test_known_ed2k_hello_world(tmp_path):
    path = tmp_path / "hello.txt"
    path.write_bytes(b"hello world")
    link = hash_file(path)
    assert link.file_hash.hex() == "aa010fbc1d14c795d86ef98c95479d17"
    assert link.to_uri() == "ed2k://|file|hello.txt|11|AA010FBC1D14C795D86EF98C95479D17|/"
