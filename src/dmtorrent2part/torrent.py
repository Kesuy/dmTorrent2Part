from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bencode import BencodeError, decode


class TorrentError(ValueError):
    pass


def _declared_encoding(root: dict[bytes, Any]) -> str | None:
    value = root.get(b"encoding")
    if isinstance(value, bytes):
        try:
            name = value.decode("ascii", errors="strict").strip()
            codecs.lookup(name)
            return name
        except (UnicodeError, LookupError):
            pass
    codepage = root.get(b"codepage")
    if isinstance(codepage, bytes):
        try:
            codepage = int(codepage)
        except ValueError:
            codepage = None
    if isinstance(codepage, int) and 1 <= codepage <= 65535:
        name = f"cp{codepage}"
        try:
            codecs.lookup(name)
            return name
        except LookupError:
            pass
    return None


def _text(value: bytes, encoding: str | None = None) -> str:
    if not isinstance(value, bytes):
        return str(value)
    for candidate in ("utf-8", encoding):
        if not candidate:
            continue
        try:
            return value.decode(candidate, errors="strict")
        except (UnicodeError, LookupError):
            continue
    return value.decode("utf-8", errors="replace")


def _hash16(value: Any) -> bytes | None:
    if isinstance(value, bytes):
        if len(value) == 16:
            return value
        if len(value) == 32:
            try:
                return bytes.fromhex(value.decode("ascii"))
            except (UnicodeError, ValueError):
                return None
    if isinstance(value, str) and len(value) == 32:
        try:
            return bytes.fromhex(value)
        except ValueError:
            return None
    return None


def _global_ed2k(value: Any, index: int, count: int) -> bytes | None:
    direct = _hash16(value)
    if direct is not None and count == 1:
        return direct
    if isinstance(value, bytes) and count > 0 and len(value) == 16 * count:
        return value[index * 16 : (index + 1) * 16]
    if isinstance(value, list) and len(value) == count:
        return _hash16(value[index])
    return None


def _is_pad(path: str, attrs: Any = None) -> bool:
    if isinstance(attrs, bytes) and b"p" in attrs:
        return True
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    return bool(parts and parts[0] == ".pad")


@dataclass(frozen=True)
class TorrentFile:
    index: int
    path: str
    length: int
    start: int
    ed2k_hash: bytes | None = None
    is_pad: bool = False

    @property
    def end(self) -> int:
        return self.start + self.length

    @property
    def name(self) -> str:
        return self.path.replace("\\", "/").rsplit("/", 1)[-1]


@dataclass(frozen=True)
class TorrentMeta:
    name: str
    piece_length: int
    pieces: tuple[bytes, ...]
    files: tuple[TorrentFile, ...]
    total_size: int
    meta_version: int = 1
    is_hybrid: bool = False
    v1_compatible: bool = True
    warning: str = ""

    @classmethod
    def from_file(cls, path: str | Path) -> "TorrentMeta":
        try:
            root = decode(Path(path).read_bytes())
        except (OSError, BencodeError) as exc:
            raise TorrentError(f"无法读取 torrent：{exc}") from exc
        if not isinstance(root, dict) or not isinstance(root.get(b"info"), dict):
            raise TorrentError("torrent 缺少 info 字典")
        info: dict[bytes, Any] = root[b"info"]
        encoding = _declared_encoding(root)
        name_raw = info.get(b"name.utf-8", info.get(b"name", b"torrent"))
        name = _text(name_raw, encoding) if isinstance(name_raw, bytes) else "torrent"

        meta_version = info.get(b"meta version", 1)
        if not isinstance(meta_version, int):
            meta_version = 1
        has_v2 = meta_version == 2 and isinstance(info.get(b"file tree"), dict)
        has_v1_layout = b"files" in info or b"length" in info
        raw_pieces = info.get(b"pieces")
        piece_length = info.get(b"piece length", 0)
        if not isinstance(piece_length, int) or piece_length < 0:
            piece_length = 0
        pieces: tuple[bytes, ...] = ()
        pieces_valid = isinstance(raw_pieces, bytes) and len(raw_pieces) % 20 == 0
        if pieces_valid:
            pieces = tuple(raw_pieces[i : i + 20] for i in range(0, len(raw_pieces), 20))

        if has_v1_layout:
            files, total = _parse_v1_files(info, name, encoding)
        elif has_v2:
            files, total = _parse_v2_files(info[b"file tree"], encoding, info.get(b"ed2k"))
        else:
            if meta_version > 2:
                raise TorrentError(f"暂不支持 BitTorrent meta version {meta_version}")
            raise TorrentError("torrent 缺少可识别的文件列表")

        warnings: list[str] = []
        v1_compatible = False
        if pieces and piece_length > 0 and has_v1_layout:
            expected = (total + piece_length - 1) // piece_length if total else 0
            if len(pieces) == expected:
                v1_compatible = True
            else:
                warnings.append(f"v1 分片数异常：记录 {len(pieces)}，按总大小应为 {expected}；仅影响旧版 Part 转换")
        elif has_v1_layout:
            warnings.append("缺少可用的 v1 pieces；仍可读取文件列表和 ED2K 信息")

        is_hybrid = bool(has_v2 and has_v1_layout and pieces)
        return cls(
            name=name,
            piece_length=piece_length,
            pieces=pieces,
            files=tuple(files),
            total_size=total,
            meta_version=2 if has_v2 else 1,
            is_hybrid=is_hybrid,
            v1_compatible=v1_compatible,
            warning="；".join(warnings),
        )


def _parse_v1_files(
    info: dict[bytes, Any], name: str, encoding: str | None
) -> tuple[list[TorrentFile], int]:
    files: list[TorrentFile] = []
    cursor = 0
    if b"files" in info:
        raw_files = info[b"files"]
        if not isinstance(raw_files, list):
            raise TorrentError("torrent files 字段无效")
        count = len(raw_files)
        global_hashes = info.get(b"ed2k")
        for idx, entry in enumerate(raw_files):
            if not isinstance(entry, dict) or not isinstance(entry.get(b"length"), int):
                raise TorrentError("torrent 文件条目无效")
            length = entry[b"length"]
            parts = entry.get(b"path.utf-8", entry.get(b"path"))
            if length < 0 or not isinstance(parts, list):
                raise TorrentError("torrent 文件路径或大小无效")
            text_parts = [_text(p, encoding) for p in parts if isinstance(p, bytes)]
            rel = "/".join(p for p in text_parts if p != "")
            if not rel:
                rel = f"unnamed-{idx}"
            ed2k_hash = _hash16(entry.get(b"ed2k")) or _global_ed2k(global_hashes, idx, count)
            files.append(
                TorrentFile(
                    idx,
                    rel,
                    length,
                    cursor,
                    ed2k_hash=ed2k_hash,
                    is_pad=_is_pad(rel, entry.get(b"attr")),
                )
            )
            cursor += length
    else:
        length = info.get(b"length")
        if not isinstance(length, int) or length < 0:
            raise TorrentError("torrent 文件大小无效")
        ed2k_hash = _hash16(info.get(b"ed2k"))
        files.append(TorrentFile(0, name, length, 0, ed2k_hash=ed2k_hash, is_pad=False))
        cursor = length
    return files, cursor


def _parse_v2_files(
    tree: dict[bytes, Any], encoding: str | None, global_ed2k: Any = None
) -> tuple[list[TorrentFile], int]:
    raw: list[tuple[str, int, bytes | None, bool]] = []

    def walk(node: Any, prefix: list[str]) -> None:
        if not isinstance(node, dict):
            return
        props = node.get(b"")
        if isinstance(props, dict) and isinstance(props.get(b"length"), int) and prefix:
            length = props[b"length"]
            if length < 0:
                raise TorrentError("v2 torrent 文件大小无效")
            path = "/".join(prefix)
            raw.append((path, length, _hash16(props.get(b"ed2k")), _is_pad(path, props.get(b"attr"))))
            return
        for key in sorted(k for k in node.keys() if k != b""):
            if not isinstance(key, bytes):
                continue
            walk(node[key], prefix + [_text(key, encoding)])

    walk(tree, [])
    if not raw:
        raise TorrentError("v2 torrent file tree 中没有文件")
    files: list[TorrentFile] = []
    cursor = 0
    count = len(raw)
    for idx, (path, length, ed2k_hash, is_pad) in enumerate(raw):
        effective_hash = ed2k_hash or _global_ed2k(global_ed2k, idx, count)
        files.append(TorrentFile(idx, path, length, cursor, effective_hash, is_pad))
        cursor += length
    return files, cursor
