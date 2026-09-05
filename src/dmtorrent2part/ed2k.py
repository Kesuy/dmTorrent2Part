from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote

try:
    from Crypto.Hash import MD4 as _CryptoMD4
except ImportError:  # optional fast path; pure Python fallback remains available
    _CryptoMD4 = None

ED2K_CHUNK_SIZE = 9_728_000


class Ed2kError(ValueError):
    pass


def _rol(value: int, bits: int) -> int:
    value &= 0xFFFFFFFF
    return ((value << bits) | (value >> (32 - bits))) & 0xFFFFFFFF


def md4(data: bytes) -> bytes:
    if _CryptoMD4 is not None:
        return _CryptoMD4.new(data=data).digest()
    return _md4_python(data)


def _md4_python(data: bytes) -> bytes:
    bit_length = (len(data) * 8) & 0xFFFFFFFFFFFFFFFF
    padded = data + b"\x80"
    padded += b"\x00" * ((56 - len(padded) % 64) % 64)
    padded += struct.pack("<Q", bit_length)

    a = 0x67452301
    b = 0xEFCDAB89
    c = 0x98BADCFE
    d = 0x10325476

    def f(x: int, y: int, z: int) -> int:
        return (x & y) | (~x & z)

    def g(x: int, y: int, z: int) -> int:
        return (x & y) | (x & z) | (y & z)

    def h(x: int, y: int, z: int) -> int:
        return x ^ y ^ z

    for off in range(0, len(padded), 64):
        x = struct.unpack("<16I", padded[off : off + 64])
        aa, bb, cc, dd = a, b, c, d

        for i in range(16):
            s = (3, 7, 11, 19)[i % 4]
            if i % 4 == 0:
                a = _rol(a + f(b, c, d) + x[i], s)
            elif i % 4 == 1:
                d = _rol(d + f(a, b, c) + x[i], s)
            elif i % 4 == 2:
                c = _rol(c + f(d, a, b) + x[i], s)
            else:
                b = _rol(b + f(c, d, a) + x[i], s)

        order2 = (0, 4, 8, 12, 1, 5, 9, 13, 2, 6, 10, 14, 3, 7, 11, 15)
        for i, k in enumerate(order2):
            s = (3, 5, 9, 13)[i % 4]
            if i % 4 == 0:
                a = _rol(a + g(b, c, d) + x[k] + 0x5A827999, s)
            elif i % 4 == 1:
                d = _rol(d + g(a, b, c) + x[k] + 0x5A827999, s)
            elif i % 4 == 2:
                c = _rol(c + g(d, a, b) + x[k] + 0x5A827999, s)
            else:
                b = _rol(b + g(c, d, a) + x[k] + 0x5A827999, s)

        order3 = (0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15)
        for i, k in enumerate(order3):
            s = (3, 9, 11, 15)[i % 4]
            if i % 4 == 0:
                a = _rol(a + h(b, c, d) + x[k] + 0x6ED9EBA1, s)
            elif i % 4 == 1:
                d = _rol(d + h(a, b, c) + x[k] + 0x6ED9EBA1, s)
            elif i % 4 == 2:
                c = _rol(c + h(d, a, b) + x[k] + 0x6ED9EBA1, s)
            else:
                b = _rol(b + h(c, d, a) + x[k] + 0x6ED9EBA1, s)

        a = (a + aa) & 0xFFFFFFFF
        b = (b + bb) & 0xFFFFFFFF
        c = (c + cc) & 0xFFFFFFFF
        d = (d + dd) & 0xFFFFFFFF

    return struct.pack("<4I", a, b, c, d)


@dataclass(frozen=True)
class Ed2kLink:
    name: str
    size: int
    file_hash: bytes
    part_hashes: tuple[bytes, ...] = ()

    @classmethod
    def parse(cls, text: str) -> "Ed2kLink":
        raw = text.strip()
        if not raw.lower().startswith("ed2k://|file|"):
            raise Ed2kError("不是有效的 ed2k 文件链接")
        parts = raw.split("|")
        if len(parts) < 6 or parts[1].lower() != "file":
            raise Ed2kError("ed2k 链接格式无效")
        name = unquote(parts[2])
        try:
            size = int(parts[3])
        except ValueError as exc:
            raise Ed2kError("ed2k 文件大小无效") from exc
        if size < 0:
            raise Ed2kError("ed2k 文件大小无效")
        file_hash = _parse_md4(parts[4], "文件哈希")
        part_hashes: tuple[bytes, ...] = ()
        for field in parts[5:]:
            if field.lower().startswith("p="):
                values = [v for v in field[2:].split(":") if v]
                part_hashes = tuple(_parse_md4(v, "分块哈希") for v in values)
                break
        return cls(name=name, size=size, file_hash=file_hash, part_hashes=part_hashes)

    @classmethod
    def from_hash(cls, name: str, size: int, file_hash: bytes) -> "Ed2kLink":
        if len(file_hash) != 16:
            raise Ed2kError("ED2K 哈希必须为 16 字节")
        return cls(name=name, size=size, file_hash=file_hash)

    def to_uri(self, include_parts: bool = False) -> str:
        filename = quote(self.name, safe="!$'()+,-.;=@[]^_`{}~")
        fields = ["ed2k://", "file", filename, str(self.size), self.file_hash.hex().upper()]
        if include_parts and self.part_hashes:
            fields.append("p=" + ":".join(h.hex().upper() for h in self.part_hashes))
        return "|".join(fields) + "|/"


def hash_file(
    path: str | Path,
    *,
    display_name: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Ed2kLink:
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise Ed2kError(f"无法读取文件：{exc}") from exc
    if not file_path.is_file():
        raise Ed2kError("请选择有效的本地文件")

    part_hashes: list[bytes] = []
    done = 0
    try:
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(ED2K_CHUNK_SIZE)
                if not chunk:
                    break
                part_hashes.append(md4(chunk))
                done += len(chunk)
                if progress:
                    progress(done, size)
    except OSError as exc:
        raise Ed2kError(f"读取文件失败：{exc}") from exc

    if size < ED2K_CHUNK_SIZE:
        file_hash = part_hashes[0] if part_hashes else md4(b"")
        exposed_parts: tuple[bytes, ...] = ()
    else:
        hashes_for_root = list(part_hashes)
        if size % ED2K_CHUNK_SIZE == 0:
            hashes_for_root.append(md4(b""))
        file_hash = md4(b"".join(hashes_for_root))
        exposed_parts = tuple(part_hashes)
    if progress:
        progress(size, size)
    return Ed2kLink(display_name or file_path.name, size, file_hash, exposed_parts)


def _parse_md4(value: str, label: str) -> bytes:
    value = value.strip()
    if len(value) != 32:
        raise Ed2kError(f"{label}必须是 32 位十六进制")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise Ed2kError(f"{label}不是有效十六进制") from exc
