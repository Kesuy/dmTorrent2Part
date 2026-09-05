from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bencode import BencodeError, decode


class TorrentError(ValueError):
    pass


def _text(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class TorrentFile:
    index: int
    path: str
    length: int
    start: int

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True)
class TorrentMeta:
    name: str
    piece_length: int
    pieces: tuple[bytes, ...]
    files: tuple[TorrentFile, ...]
    total_size: int

    @classmethod
    def from_file(cls, path: str | Path) -> "TorrentMeta":
        try:
            root = decode(Path(path).read_bytes())
        except (OSError, BencodeError) as exc:
            raise TorrentError(f"无法读取 torrent：{exc}") from exc
        if not isinstance(root, dict) or not isinstance(root.get(b"info"), dict):
            raise TorrentError("torrent 缺少 info 字典")
        info = root[b"info"]
        try:
            piece_length = int(info[b"piece length"])
            raw_pieces = info[b"pieces"]
        except KeyError as exc:
            if b"meta version" in info:
                raise TorrentError("当前仅支持 BitTorrent v1 或包含 v1 pieces 的混合种子") from exc
            raise TorrentError("torrent 缺少 v1 分片信息") from exc
        if piece_length <= 0 or not isinstance(raw_pieces, bytes) or len(raw_pieces) % 20:
            raise TorrentError("torrent 分片信息无效")
        pieces = tuple(raw_pieces[i : i + 20] for i in range(0, len(raw_pieces), 20))
        name = _text(info.get(b"name.utf-8", info.get(b"name", b"torrent")))

        files: list[TorrentFile] = []
        cursor = 0
        if b"files" in info:
            raw_files = info[b"files"]
            if not isinstance(raw_files, list):
                raise TorrentError("torrent files 字段无效")
            for idx, entry in enumerate(raw_files):
                if not isinstance(entry, dict) or b"length" not in entry:
                    raise TorrentError("torrent 文件条目无效")
                length = int(entry[b"length"])
                parts = entry.get(b"path.utf-8", entry.get(b"path"))
                if length < 0 or not isinstance(parts, list):
                    raise TorrentError("torrent 文件路径或大小无效")
                rel = "/".join(_text(p) for p in parts if isinstance(p, bytes))
                files.append(TorrentFile(idx, rel, length, cursor))
                cursor += length
        else:
            if b"length" not in info:
                raise TorrentError("torrent 缺少文件大小")
            length = int(info[b"length"])
            if length < 0:
                raise TorrentError("torrent 文件大小无效")
            files.append(TorrentFile(0, name, length, 0))
            cursor = length

        expected_piece_count = (cursor + piece_length - 1) // piece_length if cursor else 0
        if len(pieces) != expected_piece_count:
            raise TorrentError(
                f"torrent 分片数不匹配：记录 {len(pieces)}，按总大小应为 {expected_piece_count}"
            )
        return cls(name, piece_length, pieces, tuple(files), cursor)
