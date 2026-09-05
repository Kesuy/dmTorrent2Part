from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .ed2k import Ed2kLink
from .partmet import PartMetInfo, write_part_met
from .torrent import TorrentFile, TorrentMeta
from .verify import VerificationResult, verify_file


@dataclass(frozen=True)
class ConversionResult:
    part_path: Path | None
    met_path: Path
    verification: VerificationResult


def convert(
    torrent: TorrentMeta,
    target: TorrentFile,
    incomplete_path: str | Path,
    ed2k: Ed2kLink,
    output_dir: str | Path,
    part_number: int = 1,
    met_only: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> ConversionResult:
    if target.length != ed2k.size:
        raise ValueError(f"torrent 文件大小与 ED2K 链接不一致：{target.length} != {ed2k.size}")
    if part_number < 1 or part_number > 999:
        raise ValueError("part 编号必须在 1-999 之间")

    source = Path(incomplete_path)
    verification = verify_file(torrent, target, source, progress)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{part_number:03d}.part"
    part_path = out_dir / stem
    met_path = out_dir / f"{stem}.met"

    if not met_only:
        _write_sparse_verified_part(source, part_path, target.length, verification.verified_ranges)

    info = PartMetInfo(
        filename=ed2k.name or Path(target.path).name,
        file_size=target.length,
        file_hash=ed2k.file_hash,
        part_hashes=ed2k.part_hashes,
        gaps=verification.gaps,
        transferred=verification.verified_bytes,
    )
    timestamp = int(source.stat().st_mtime)
    write_part_met(met_path, info, timestamp=timestamp)
    return ConversionResult(None if met_only else part_path, met_path, verification)


def _write_sparse_verified_part(
    source: Path,
    output: Path,
    full_size: int,
    ranges: tuple[tuple[int, int], ...],
    chunk_size: int = 4 * 1024 * 1024,
) -> None:
    tmp = output.with_suffix(output.suffix + ".tmp")
    try:
        with source.open("rb") as src, tmp.open("w+b") as dst:
            dst.truncate(full_size)
            for start, end in ranges:
                src.seek(start)
                dst.seek(start)
                remaining = end - start
                while remaining:
                    block = src.read(min(chunk_size, remaining))
                    if not block:
                        raise OSError("源文件在复制已验证区域时提前结束")
                    dst.write(block)
                    remaining -= len(block)
        os.replace(tmp, output)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
