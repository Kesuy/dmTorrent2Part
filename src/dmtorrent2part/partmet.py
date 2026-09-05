from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable


PARTFILE_VERSION = 0xE0
PARTFILE_VERSION_LARGEFILE = 0xE2
TAGTYPE_STRING = 0x02
TAGTYPE_UINT32 = 0x03
TAGTYPE_UINT64 = 0x0B

FT_FILENAME = 0x01
FT_FILESIZE = 0x02
FT_TRANSFERRED = 0x08
FT_GAPSTART = 0x09
FT_GAPEND = 0x0A
FT_STATUS = 0x14


@dataclass(frozen=True)
class PartMetInfo:
    filename: str
    file_size: int
    file_hash: bytes
    part_hashes: tuple[bytes, ...]
    gaps: tuple[tuple[int, int], ...]  # inclusive
    transferred: int


def write_part_met(path: str | Path, info: PartMetInfo, timestamp: int | None = None) -> None:
    if len(info.file_hash) != 16:
        raise ValueError("ED2K 文件哈希必须为 16 字节")
    if any(len(h) != 16 for h in info.part_hashes):
        raise ValueError("ED2K 分块哈希必须为 16 字节")
    if info.file_size < 0:
        raise ValueError("文件大小不能为负数")
    large = info.file_size >= 2**32
    version = PARTFILE_VERSION_LARGEFILE if large else PARTFILE_VERSION
    ts = int(time.time() if timestamp is None else timestamp) & 0xFFFFFFFF

    tags: list[bytes] = [
        _tag_string_id(FT_FILENAME, info.filename),
        _tag_int_id(FT_FILESIZE, info.file_size, 64 if large else 32),
        _tag_int_id(FT_TRANSFERRED, info.transferred, 64 if large else 32),
        _tag_int_id(FT_STATUS, 0, 32),
    ]
    for idx, (start, end) in enumerate(info.gaps):
        if not (0 <= start <= end < info.file_size):
            raise ValueError(f"无效缺口：{start}-{end}")
        # eMule/aMule stores a string tag name whose first byte is FT_GAPSTART/END,
        # followed by the decimal gap number. GAPEND is exclusive on disk.
        tags.append(_tag_int_name(bytes([FT_GAPSTART]) + str(idx).encode("ascii"), start, 64 if large else 32))
        tags.append(_tag_int_name(bytes([FT_GAPEND]) + str(idx).encode("ascii"), end + 1, 64 if large else 32))

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        f.write(struct.pack("<BI", version, ts))
        f.write(info.file_hash)
        f.write(struct.pack("<H", len(info.part_hashes)))
        for part_hash in info.part_hashes:
            f.write(part_hash)
        f.write(struct.pack("<I", len(tags)))
        for tag in tags:
            f.write(tag)


def _tag_string_id(name_id: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return bytes([TAGTYPE_STRING]) + struct.pack("<H", 1) + bytes([name_id]) + struct.pack("<H", len(raw)) + raw


def _tag_int_id(name_id: int, value: int, bits: int) -> bytes:
    if bits == 64:
        return bytes([TAGTYPE_UINT64]) + struct.pack("<H", 1) + bytes([name_id]) + struct.pack("<Q", value)
    return bytes([TAGTYPE_UINT32]) + struct.pack("<H", 1) + bytes([name_id]) + struct.pack("<I", value)


def _tag_int_name(name: bytes, value: int, bits: int) -> bytes:
    tag_type = TAGTYPE_UINT64 if bits == 64 else TAGTYPE_UINT32
    payload = struct.pack("<Q" if bits == 64 else "<I", value)
    return bytes([tag_type]) + struct.pack("<H", len(name)) + name + payload


def read_part_met(path: str | Path) -> dict[str, object]:
    """Small structural reader used by tests/diagnostics; not a full eMule parser."""
    with Path(path).open("rb") as f:
        version, timestamp = struct.unpack("<BI", _read_exact(f, 5))
        file_hash = _read_exact(f, 16)
        count = struct.unpack("<H", _read_exact(f, 2))[0]
        part_hashes = [_read_exact(f, 16) for _ in range(count)]
        tag_count = struct.unpack("<I", _read_exact(f, 4))[0]
        tags = [_read_tag(f) for _ in range(tag_count)]
        if f.read(1):
            raise ValueError("part.met 末尾存在未解析数据")
    return {
        "version": version,
        "timestamp": timestamp,
        "file_hash": file_hash,
        "part_hashes": part_hashes,
        "tags": tags,
    }


def _read_tag(f: BinaryIO) -> tuple[int, bytes, int | str]:
    tag_type = _read_exact(f, 1)[0]
    name_len = struct.unpack("<H", _read_exact(f, 2))[0]
    name = _read_exact(f, name_len)
    if tag_type == TAGTYPE_STRING:
        length = struct.unpack("<H", _read_exact(f, 2))[0]
        value: int | str = _read_exact(f, length).decode("utf-8", errors="replace")
    elif tag_type == TAGTYPE_UINT32:
        value = struct.unpack("<I", _read_exact(f, 4))[0]
    elif tag_type == TAGTYPE_UINT64:
        value = struct.unpack("<Q", _read_exact(f, 8))[0]
    else:
        raise ValueError(f"不支持的 tag type 0x{tag_type:02X}")
    return tag_type, name, value


def _read_exact(f: BinaryIO, size: int) -> bytes:
    data = f.read(size)
    if len(data) != size:
        raise ValueError("part.met 被截断")
    return data
