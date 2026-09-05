from __future__ import annotations

import argparse
from pathlib import Path

from .core import convert
from .ed2k import Ed2kLink
from .torrent import TorrentMeta


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dmTorrent2Part", description="将 BT 未完成文件转换为 eMule .part/.part.met")
    p.add_argument("torrent", help=".torrent 文件")
    p.add_argument("incomplete", help="BT 未完成文件")
    p.add_argument("ed2k", help="目标文件的 ed2k:// 链接")
    p.add_argument("-o", "--output", default=".", help="输出目录")
    p.add_argument("-i", "--index", type=int, default=0, help="torrent 文件索引（多文件种子）")
    p.add_argument("-n", "--part-number", type=int, default=1, help="eMule part 编号，默认 1")
    p.add_argument("--met-only", action="store_true", help="仅生成 .part.met")
    p.add_argument("--list", action="store_true", help="列出 torrent 内文件后退出")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    torrent = TorrentMeta.from_file(args.torrent)
    if args.list:
        for f in torrent.files:
            print(f"[{f.index}] {f.length:>12}  {f.path}")
        return 0
    if not (0 <= args.index < len(torrent.files)):
        raise SystemExit(f"文件索引超出范围：0-{len(torrent.files)-1}")
    target = torrent.files[args.index]
    ed2k = Ed2kLink.parse(args.ed2k)
    result = convert(
        torrent,
        target,
        args.incomplete,
        ed2k,
        args.output,
        part_number=args.part_number,
        met_only=args.met_only,
    )
    v = result.verification
    print(f"完成：已验证 {v.verified_bytes}/{target.length} 字节，匹配分片 {v.matched_pieces}/{v.checked_pieces}")
    if result.part_path:
        print(f"PART: {result.part_path}")
    print(f"MET : {result.met_path}")
    if v.skipped_boundary_bytes:
        print(f"提示：多文件 torrent 边界分片有 {v.skipped_boundary_bytes} 字节无法单文件验证，已保守标记为缺口。")
    return 0
