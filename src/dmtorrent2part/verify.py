from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Callable, Iterable

from .torrent import TorrentFile, TorrentMeta


Progress = Callable[[int, int], None]


@dataclass(frozen=True)
class VerificationResult:
    verified_ranges: tuple[tuple[int, int], ...]  # [start, end)
    gaps: tuple[tuple[int, int], ...]  # inclusive [start, end]
    verified_bytes: int
    checked_pieces: int
    matched_pieces: int
    skipped_boundary_bytes: int


def verify_file(
    torrent: TorrentMeta,
    target: TorrentFile,
    incomplete_path: str | Path,
    progress: Progress | None = None,
) -> VerificationResult:
    path = Path(incomplete_path)
    try:
        actual_size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"无法读取未完成文件：{exc}") from exc
    if actual_size > target.length:
        raise ValueError(f"未完成文件比 torrent 目标文件更大（{actual_size} > {target.length}）")

    first_piece = target.start // torrent.piece_length
    last_piece = (target.end - 1) // torrent.piece_length if target.length else first_piece - 1
    candidate_count = max(0, last_piece - first_piece + 1)
    verified: list[tuple[int, int]] = []
    checked = matched = 0
    boundary_skipped = 0

    with path.open("rb") as f:
        for done, piece_index in enumerate(range(first_piece, last_piece + 1), start=1):
            piece_start = piece_index * torrent.piece_length
            piece_end = min(torrent.total_size, piece_start + torrent.piece_length)

            # A v1 piece may span adjacent files. We cannot verify that SHA-1 from one file alone,
            # so conservatively keep the overlapping bytes as a gap.
            if piece_start < target.start or piece_end > target.end:
                overlap_start = max(piece_start, target.start)
                overlap_end = min(piece_end, target.end)
                boundary_skipped += max(0, overlap_end - overlap_start)
                if progress:
                    progress(done, candidate_count)
                continue

            local_start = piece_start - target.start
            local_end = piece_end - target.start
            if local_end > actual_size:
                if progress:
                    progress(done, candidate_count)
                continue

            f.seek(local_start)
            data = f.read(local_end - local_start)
            checked += 1
            if len(data) == local_end - local_start and sha1(data).digest() == torrent.pieces[piece_index]:
                verified.append((local_start, local_end))
                matched += 1
            if progress:
                progress(done, candidate_count)

    merged = tuple(_merge_ranges(verified))
    gaps = tuple(_ranges_to_gaps(target.length, merged))
    verified_bytes = sum(end - start for start, end in merged)
    return VerificationResult(merged, gaps, verified_bytes, checked, matched, boundary_skipped)


def _merge_ranges(ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted((a, b) for a, b in ranges if b > a)
    if not ordered:
        return []
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        old_start, old_end = merged[-1]
        if start <= old_end:
            merged[-1] = (old_start, max(old_end, end))
        else:
            merged.append((start, end))
    return merged


def _ranges_to_gaps(size: int, verified: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    if size <= 0:
        return []
    cursor = 0
    gaps: list[tuple[int, int]] = []
    for start, end in verified:
        start = max(0, min(size, start))
        end = max(start, min(size, end))
        if start > cursor:
            gaps.append((cursor, start - 1))
        cursor = max(cursor, end)
    if cursor < size:
        gaps.append((cursor, size - 1))
    return gaps
