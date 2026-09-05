from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote


class Ed2kError(ValueError):
    pass


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


def _parse_md4(value: str, label: str) -> bytes:
    value = value.strip()
    if len(value) != 32:
        raise Ed2kError(f"{label}必须是 32 位十六进制")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise Ed2kError(f"{label}不是有效十六进制") from exc
