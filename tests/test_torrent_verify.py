from hashlib import sha1

from dmtorrent2part.bencode import encode
from dmtorrent2part.torrent import TorrentMeta
from dmtorrent2part.verify import verify_file


def test_single_file_verification(tmp_path):
    piece_len = 4
    data = b"abcdefghij"
    pieces = b"".join(sha1(data[i:i+piece_len]).digest() for i in range(0, len(data), piece_len))
    torrent_path = tmp_path / "x.torrent"
    torrent_path.write_bytes(encode({b"info": {b"name": b"x.bin", b"length": len(data), b"piece length": piece_len, b"pieces": pieces}}))
    partial = tmp_path / "x.bin"
    partial.write_bytes(b"abcdXXXXij")

    meta = TorrentMeta.from_file(torrent_path)
    result = verify_file(meta, meta.files[0], partial)
    assert result.verified_ranges == ((0, 4), (8, 10))
    assert result.gaps == ((4, 7),)
    assert result.verified_bytes == 6
