from hashlib import sha1

from dmtorrent2part.bencode import encode
from dmtorrent2part.torrent import TorrentMeta


H1 = bytes.fromhex("00112233445566778899aabbccddeeff")
H2 = bytes.fromhex("ffeeddccbbaa99887766554433221100")


def test_single_file_embedded_ed2k(tmp_path):
    p = tmp_path / "one.torrent"
    p.write_bytes(encode({b"info": {
        b"name": b"a.bin", b"length": 1, b"piece length": 1,
        b"pieces": sha1(b"x").digest(), b"ed2k": H1,
    }}))
    meta = TorrentMeta.from_file(p)
    assert meta.v1_compatible
    assert meta.files[0].ed2k_hash == H1


def test_multi_file_global_ed2k_table(tmp_path):
    p = tmp_path / "multi.torrent"
    p.write_bytes(encode({b"info": {
        b"name": b"pack", b"piece length": 1,
        b"pieces": sha1(b"a").digest() + sha1(b"b").digest(),
        b"ed2k": H1 + H2,
        b"files": [
            {b"length": 1, b"path": [b"dir", b"a.bin"]},
            {b"length": 1, b"path": [b"dir", b"b.bin"]},
        ],
    }}))
    meta = TorrentMeta.from_file(p)
    assert [f.ed2k_hash for f in meta.files] == [H1, H2]
    assert [f.path for f in meta.files] == ["dir/a.bin", "dir/b.bin"]


def test_v2_file_tree_without_v1_pieces(tmp_path):
    p = tmp_path / "v2.torrent"
    p.write_bytes(encode({b"info": {
        b"name": b"v2", b"meta version": 2, b"piece length": 16384,
        b"file tree": {
            b"dir": {
                b"a.bin": {b"": {b"length": 10, b"pieces root": b"x" * 32, b"ed2k": H1}},
                b"b.bin": {b"": {b"length": 20, b"pieces root": b"y" * 32}},
            }
        },
    }}))
    meta = TorrentMeta.from_file(p)
    assert meta.meta_version == 2
    assert not meta.v1_compatible
    assert [f.path for f in meta.files] == ["dir/a.bin", "dir/b.bin"]
    assert meta.files[0].ed2k_hash == H1


def test_v2_global_ed2k_table(tmp_path):
    p = tmp_path / "v2-global.torrent"
    p.write_bytes(encode({b"info": {
        b"name": b"v2", b"meta version": 2, b"piece length": 16384,
        b"ed2k": H1 + H2,
        b"file tree": {
            b"a.bin": {b"": {b"length": 10, b"pieces root": b"x" * 32}},
            b"b.bin": {b"": {b"length": 20, b"pieces root": b"y" * 32}},
        },
    }}))
    meta = TorrentMeta.from_file(p)
    assert [f.ed2k_hash for f in meta.files] == [H1, H2]


def test_declared_gbk_path(tmp_path):
    p = tmp_path / "gbk.torrent"
    chinese = "测试.txt".encode("gbk")
    p.write_bytes(encode({
        b"encoding": b"GBK",
        b"info": {
            b"name": b"root", b"piece length": 1, b"pieces": sha1(b"x").digest(),
            b"files": [{b"length": 1, b"path": [chinese]}],
        },
    }))
    meta = TorrentMeta.from_file(p)
    assert meta.files[0].path == "测试.txt"
