from __future__ import annotations

import argparse
from pathlib import Path

from .core import convert
from .ed2k import Ed2kLink, hash_file
from .torrent import TorrentFile, TorrentMeta


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dmTorrent2Part",
        description="优先从 torrent 提取/生成 ED2K 链接；同时保留旧版 BT 未完成文件 → eMule Part 转换。",
    )
    p.add_argument("torrent", help=".torrent 文件")
    p.add_argument("incomplete", nargs="?", help="兼容模式：BT 未完成文件")
    p.add_argument("ed2k", nargs="?", help="兼容模式：目标文件的 ed2k:// 链接")
    p.add_argument("-i", "--index", type=int, default=0, help="文件索引，默认 0")
    p.add_argument("--root", help="本地下载根目录；为缺少内置 ED2K 的文件计算链接")
    p.add_argument("--local-file", help="为 --index 指定的单个 torrent 文件计算 ED2K")
    p.add_argument("--list", action="store_true", help="列出 torrent 文件和 ED2K 状态")
    p.add_argument("-o", "--output", default=".", help="兼容模式输出目录")
    p.add_argument("-n", "--part-number", type=int, default=1, help="兼容模式 eMule part 编号")
    p.add_argument("--met-only", action="store_true", help="兼容模式仅生成 .part.met")
    return p


def _embedded_link(file: TorrentFile) -> Ed2kLink | None:
    if file.ed2k_hash is None:
        return None
    return Ed2kLink.from_hash(file.name, file.length, file.ed2k_hash)


def _resolve_local(root: Path, torrent: TorrentMeta, target: TorrentFile) -> Path | None:
    rel = Path(*[p for p in target.path.replace("\\", "/").split("/") if p])
    candidates = [root / rel, root / torrent.name / rel]
    if len(torrent.files) == 1:
        candidates.insert(0, root / target.name)
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate.stat().st_size == target.length:
                return candidate
        except OSError:
            continue
    return None


def _print_files(meta: TorrentMeta) -> None:
    for file in meta.files:
        if file.is_pad:
            status = "[padding]"
        elif file.ed2k_hash:
            status = _embedded_link(file).to_uri()
        else:
            status = "[需要本地文件计算 ED2K]"
        print(f"[{file.index:>3}] {file.length:>12}  {file.path}  {status}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    meta = TorrentMeta.from_file(args.torrent)

    # Preserve the v1.0 command shape: torrent incomplete ed2k [...]
    if args.incomplete is not None or args.ed2k is not None:
        if not args.incomplete or not args.ed2k:
            raise SystemExit("兼容 Part 转换需要同时提供 incomplete 和 ed2k 参数")
        if not (0 <= args.index < len(meta.files)):
            raise SystemExit(f"文件索引超出范围：0-{len(meta.files)-1}")
        target = meta.files[args.index]
        result = convert(
            meta,
            target,
            args.incomplete,
            Ed2kLink.parse(args.ed2k),
            args.output,
            part_number=args.part_number,
            met_only=args.met_only,
        )
        v = result.verification
        print(f"完成：已验证 {v.verified_bytes}/{target.length} 字节，匹配分片 {v.matched_pieces}/{v.checked_pieces}")
        if result.part_path:
            print(f"PART: {result.part_path}")
        print(f"MET : {result.met_path}")
        return 0

    if args.local_file:
        if not (0 <= args.index < len(meta.files)):
            raise SystemExit(f"文件索引超出范围：0-{len(meta.files)-1}")
        target = meta.files[args.index]
        local = Path(args.local_file)
        if local.stat().st_size != target.length:
            raise SystemExit(f"本地文件大小不匹配：{local.stat().st_size} != {target.length}")
        print(hash_file(local, display_name=target.name).to_uri())
        return 0

    if args.root:
        root = Path(args.root)
        missing = 0
        for target in meta.files:
            if target.is_pad:
                continue
            embedded = _embedded_link(target)
            if embedded:
                print(embedded.to_uri())
                continue
            local = _resolve_local(root, meta, target)
            if local is None:
                missing += 1
                print(f"# 未找到本地文件：{target.path}")
                continue
            print(hash_file(local, display_name=target.name).to_uri())
        return 1 if missing else 0

    _print_files(meta)
    if meta.warning:
        print(f"提示：{meta.warning}")
    return 0
