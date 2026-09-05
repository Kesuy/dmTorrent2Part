from hashlib import sha1

from dmtorrent2part.bencode import encode
from dmtorrent2part.core import convert
from dmtorrent2part.ed2k import Ed2kLink
from dmtorrent2part.partmet import FT_GAPEND, FT_GAPSTART, read_part_met
from dmtorrent2part.torrent import TorrentMeta


def test_end_to_end_conversion(tmp_path):
    original = b"AAAABBBBCCCC"
    piece_len = 4
    pieces = b"".join(sha1(original[i:i+piece_len]).digest() for i in range(0, len(original), piece_len))
    torrent_path = tmp_path / "x.torrent"
    torrent_path.write_bytes(encode({b"info": {
        b"name": b"x.bin", b"length": len(original), b"piece length": piece_len, b"pieces": pieces
    }}))
    partial = tmp_path / "x.bin"
    partial.write_bytes(b"AAAAXXXXCCCC")
    meta = TorrentMeta.from_file(torrent_path)
    ed2k = Ed2kLink.parse("ed2k://|file|x.bin|12|0123456789ABCDEF0123456789ABCDEF|/")
    result = convert(meta, meta.files[0], partial, ed2k, tmp_path / "out")

    part = result.part_path.read_bytes()
    assert part == b"AAAA\x00\x00\x00\x00CCCC"
    parsed = read_part_met(result.met_path)
    gap_starts = [value for _, name, value in parsed["tags"] if name.startswith(bytes([FT_GAPSTART]))]
    gap_ends = [value for _, name, value in parsed["tags"] if name.startswith(bytes([FT_GAPEND]))]
    assert gap_starts == [4]
    assert gap_ends == [8]
