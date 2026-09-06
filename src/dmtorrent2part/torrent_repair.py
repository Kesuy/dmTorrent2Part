from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TorrentDiagnostic:
    valid_bencode: bool
    trailing_bytes: bytes = b""
    recoverable: bool = False
    message: str = ""


def diagnose_torrent(path: str | Path) -> TorrentDiagnostic:
    data = Path(path).read_bytes()
    # The actual bencode decoder reports the end position. Keep this module
    # intentionally small so it can be used by GUI and CLI layers.
    from .bencode import decode

    try:
        _value, end = decode(data, return_end=True)
    except Exception as exc:
        return TorrentDiagnostic(False, message=str(exc))

    trailing = data[end:]
    if not trailing:
        return TorrentDiagnostic(True, message="Torrent 格式正常")

    harmless = trailing.lstrip(b"\xef\xbb\xbf \t\r\n") == b""
    return TorrentDiagnostic(
        True,
        trailing,
        harmless,
        "发现可忽略的文件尾附加数据" if harmless else "发现异常尾部数据",
    )


def repair_torrent(path: str | Path, output: str | Path | None = None) -> Path:
    source = Path(path)
    data = source.read_bytes()
    from .bencode import decode

    _value, end = decode(data, return_end=True)
    fixed = data[:end]
    target = Path(output) if output else source.with_name(source.stem + ".fixed" + source.suffix)
    target.write_bytes(fixed)
    return target
