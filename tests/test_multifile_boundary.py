from hashlib import sha1

from dmtorrent2part.bencode import encode
from dmtorrent2part.torrent import TorrentMeta
from dmtorrent2part.verify import verify_file


def test_multifile_boundary_is_conservative(tmp_path):
    whole = b"AAAABBBBCCCC"
    piece_len = 4
    pieces = b"".join(sha1(whole[i:i+piece_len]).digest() for i in range(0, len(whole), piece_len))
    info = {
        b"name": b"root",
        b"piece length": piece_len,
        b"pieces": pieces,
        b"files": [
            {b"length": 5, b"path": [b"a.bin"]},
            {b"length": 7, b"path": [b"b.bin"]},
        ],
    }
    tp = tmp_path / "m.torrent"
    tp.write_bytes(encode({b"info": info}))
    meta = TorrentMeta.from_file(tp)
    target = meta.files[1]
    partial = tmp_path / "b.bin"
    partial.write_bytes(whole[5:])
    result = verify_file(meta, target, partial)
    # First and last target overlaps are cross-file/partial-piece boundaries; middle piece is verifiable.
    assert result.verified_ranges == ((3, 7),)
    assert result.gaps == ((0, 2),)
