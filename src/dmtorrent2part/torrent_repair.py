from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bencode import BencodeError, decode_prefix


_UTF8_BOM = b"\xef\xbb\xbf"
_ASCII_WS = b" \t\r\n"


@dataclass(frozen=True)
class TorrentDiagnostic:
    valid_bencode: bool
    recoverable: bool
    leading_bom: bool = False
    trailing_bytes: bytes = b""
    root_end: int = 0
    message: str = ""

    @property
    def has_issue(self) -> bool:
        return self.leading_bom or bool(self.trailing_bytes) or not self.valid_bencode

    @property
    def trailing_size(self) -> int:
        return len(self.trailing_bytes)


def _harmless_tail(data: bytes) -> bool:
    if not data:
        return True
    return data.replace(_UTF8_BOM, b"").strip(_ASCII_WS) == b""


def _tail_name(data: bytes) -> str:
    if not data:
        return "无"
    if data == b"\r\n":
        return "CRLF"
    if data == b"\n":
        return "LF"
    if data == b"\r":
        return "CR"
    cleaned = data.replace(_UTF8_BOM, b"").strip(_ASCII_WS)
    if not cleaned:
        parts: list[str] = []
        if _UTF8_BOM in data:
            parts.append("UTF-8 BOM")
        if any(ch in data for ch in (b"\r", b"\n")):
            parts.append("换行")
        if any(ch in data for ch in (b" ", b"\t")):
            parts.append("空白")
        return " + ".join(parts) or "可忽略空白"
    return f"非标准数据（{len(data)} 字节）"


def diagnose_bytes(data: bytes) -> TorrentDiagnostic:
    leading_bom = data.startswith(_UTF8_BOM)
    try:
        _value, end = decode_prefix(data, allow_leading_bom=True)
    except (BencodeError, ValueError) as exc:
        return TorrentDiagnostic(
            valid_bencode=False,
            recoverable=False,
            leading_bom=leading_bom,
            message=f"bencode 主体损坏：{exc}",
        )

    trailing = data[end:]
    recoverable = _harmless_tail(trailing)
    if not leading_bom and not trailing:
        message = "Torrent 格式正常，没有发现需要修复的问题。"
    elif recoverable:
        issues: list[str] = []
        if leading_bom:
            issues.append("文件头 UTF-8 BOM")
        if trailing:
            issues.append(f"文件尾 {len(trailing)} 字节 {_tail_name(trailing)}")
        message = "；".join(issues) + "。主体结构正常，可安全清理这些附加字节。"
    else:
        message = (
            f"bencode 主体可以解析，但文件尾还有 {len(trailing)} 字节 "
            f"{_tail_name(trailing)}。为避免误删有效数据，不进行自动修复。"
        )

    return TorrentDiagnostic(
        valid_bencode=True,
        recoverable=recoverable,
        leading_bom=leading_bom,
        trailing_bytes=trailing,
        root_end=end,
        message=message,
    )


def diagnose_torrent(path: str | Path) -> TorrentDiagnostic:
    return diagnose_bytes(Path(path).read_bytes())


def format_diagnostic(result: TorrentDiagnostic) -> str:
    lines = ["Torrent 检测结果", ""]
    if result.valid_bencode:
        lines.append("✓ bencode 主体可正常解析")
    else:
        lines.append("✗ bencode 主体无法解析")
        lines.extend(["", result.message])
        return "\n".join(lines)

    if result.leading_bom:
        lines.append("⚠ 文件头存在 UTF-8 BOM")
    if result.trailing_bytes:
        lines.append(
            f"⚠ 文件尾存在 {result.trailing_size} 字节：{_tail_name(result.trailing_bytes)}"
        )
    if not result.leading_bom and not result.trailing_bytes:
        lines.append("✓ 未发现额外头部/尾部数据")

    lines.extend(["", result.message])
    if result.has_issue:
        lines.extend(
            [
                "",
                "结论：" + ("可自动修复" if result.recoverable else "不建议自动修复"),
            ]
        )
    return "\n".join(lines)


def repaired_bytes(data: bytes) -> bytes:
    result = diagnose_bytes(data)
    if not result.valid_bencode:
        raise ValueError(result.message)
    if not result.has_issue:
        return data
    if not result.recoverable:
        raise ValueError(result.message)

    start = len(_UTF8_BOM) if result.leading_bom else 0
    # Keep the original bencoded bytes byte-for-byte; only a BOM before the root
    # and harmless bytes after the root are removed. The info dictionary bytes,
    # and therefore the torrent info hash, are unchanged.
    return data[start:result.root_end]


def repair_torrent(path: str | Path, output: str | Path | None = None) -> Path:
    source = Path(path)
    fixed = repaired_bytes(source.read_bytes())
    target = (
        Path(output)
        if output is not None
        else source.with_name(source.stem + ".fixed" + source.suffix)
    )
    target.write_bytes(fixed)
    return target
