from __future__ import annotations

from dmtorrent2part.bencode import BencodeError, decode, encode
from dmtorrent2part.torrent_repair import diagnose_bytes, repaired_bytes


def _torrent_bytes() -> bytes:
    return encode(
        {
            b"announce": b"https://tracker.example/announce",
            b"info": {
                b"length": 4,
                b"name": b"demo.bin",
                b"piece length": 4,
                b"pieces": b"0" * 20,
            },
        }
    )


def test_crlf_tail_is_accepted_diagnosed_and_repaired() -> None:
    clean = _torrent_bytes()
    dirty = clean + b"\r\n"

    assert decode(dirty)[b"info"][b"name"] == b"demo.bin"
    result = diagnose_bytes(dirty)
    assert result.valid_bencode
    assert result.recoverable
    assert result.trailing_bytes == b"\r\n"
    assert repaired_bytes(dirty) == clean


def test_bom_and_whitespace_combination_is_recoverable() -> None:
    clean = _torrent_bytes()
    dirty = b"\xef\xbb\xbf" + clean + b"\r\n\xef\xbb\xbf \t"

    result = diagnose_bytes(dirty)
    assert result.valid_bencode
    assert result.recoverable
    assert result.leading_bom
    assert repaired_bytes(dirty) == clean


def test_real_trailing_garbage_is_not_silently_accepted_or_repaired() -> None:
    clean = _torrent_bytes()
    dirty = clean + b"JUNK"

    try:
        decode(dirty)
    except BencodeError:
        pass
    else:
        raise AssertionError("non-whitespace garbage must be rejected")

    result = diagnose_bytes(dirty)
    assert result.valid_bencode
    assert not result.recoverable

    try:
        repaired_bytes(dirty)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe trailing data must not be auto-repaired")


def test_strict_decode_still_rejects_crlf() -> None:
    dirty = _torrent_bytes() + b"\r\n"
    try:
        decode(dirty, strict=True)
    except BencodeError:
        pass
    else:
        raise AssertionError("strict mode must reject any trailing bytes")
