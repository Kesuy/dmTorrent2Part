from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BencodeError(ValueError):
    pass


_UTF8_BOM = b"\xef\xbb\xbf"
_ASCII_WS = b" \t\r\n"


@dataclass
class _Decoder:
    data: bytes
    pos: int = 0

    def parse(self) -> Any:
        if self.pos >= len(self.data):
            raise BencodeError("unexpected end of bencoded data")
        token = self.data[self.pos : self.pos + 1]
        if token == b"i":
            return self._int()
        if token == b"l":
            return self._list()
        if token == b"d":
            return self._dict()
        if b"0" <= token <= b"9":
            return self._bytes()
        raise BencodeError(f"invalid token at offset {self.pos}: {token!r}")

    def _int(self) -> int:
        self.pos += 1
        end = self.data.find(b"e", self.pos)
        if end < 0:
            raise BencodeError("unterminated integer")
        raw = self.data[self.pos:end]
        if not raw or raw in (b"-0",) or (raw.startswith(b"0") and raw != b"0"):
            raise BencodeError("invalid integer")
        try:
            value = int(raw)
        except ValueError as exc:
            raise BencodeError("invalid integer") from exc
        self.pos = end + 1
        return value

    def _bytes(self) -> bytes:
        colon = self.data.find(b":", self.pos)
        if colon < 0:
            raise BencodeError("invalid byte string")
        raw_len = self.data[self.pos:colon]
        if not raw_len or (raw_len.startswith(b"0") and raw_len != b"0"):
            raise BencodeError("invalid byte string length")
        try:
            length = int(raw_len)
        except ValueError as exc:
            raise BencodeError("invalid byte string length") from exc
        start = colon + 1
        end = start + length
        if length < 0 or end > len(self.data):
            raise BencodeError("byte string exceeds input")
        self.pos = end
        return self.data[start:end]

    def _list(self) -> list[Any]:
        self.pos += 1
        values: list[Any] = []
        while True:
            if self.pos >= len(self.data):
                raise BencodeError("unterminated list")
            if self.data[self.pos : self.pos + 1] == b"e":
                self.pos += 1
                return values
            values.append(self.parse())

    def _dict(self) -> dict[bytes, Any]:
        self.pos += 1
        values: dict[bytes, Any] = {}
        while True:
            if self.pos >= len(self.data):
                raise BencodeError("unterminated dictionary")
            if self.data[self.pos : self.pos + 1] == b"e":
                self.pos += 1
                return values
            key = self._bytes()
            values[key] = self.parse()


def _ignorable_tail(data: bytes) -> bool:
    if not data:
        return True
    without_bom = data.replace(_UTF8_BOM, b"")
    return without_bom.strip(_ASCII_WS) == b""


def decode_prefix(data: bytes, *, allow_leading_bom: bool = True) -> tuple[Any, int]:
    """Decode the first bencoded value and return ``(value, end_offset)``.

    The returned offset refers to the original byte string. Trailing bytes are
    intentionally not validated so diagnostic/repair code can inspect them.
    """
    start = len(_UTF8_BOM) if allow_leading_bom and data.startswith(_UTF8_BOM) else 0
    decoder = _Decoder(data, start)
    value = decoder.parse()
    return value, decoder.pos


def decode(data: bytes, *, strict: bool = False, return_end: bool = False) -> Any:
    """Decode bencode with real-world torrent compatibility.

    Default mode accepts a leading UTF-8 BOM and harmless trailing combinations
    of ASCII whitespace / UTF-8 BOM. ``strict=True`` requires the bencoded
    value to occupy the entire input exactly.
    """
    value, end = decode_prefix(data, allow_leading_bom=not strict)
    trailing = data[end:]

    if strict:
        if end != len(data):
            raise BencodeError("trailing data after bencoded value")
        if data.startswith(_UTF8_BOM):
            raise BencodeError("leading UTF-8 BOM before bencoded value")
    elif not _ignorable_tail(trailing):
        raise BencodeError("trailing data after bencoded value")

    return (value, end) if return_end else value


def encode(value: Any) -> bytes:
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return encode(value.encode("utf-8"))
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, list):
        return b"l" + b"".join(encode(v) for v in value) + b"e"
    if isinstance(value, dict):
        items = []
        for key in sorted(value):
            key_bytes = key if isinstance(key, bytes) else str(key).encode("utf-8")
            items.append(encode(key_bytes))
            items.append(encode(value[key]))
        return b"d" + b"".join(items) + b"e"
    raise TypeError(f"cannot bencode {type(value)!r}")
