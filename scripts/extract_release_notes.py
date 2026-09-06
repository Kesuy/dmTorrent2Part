from __future__ import annotations

import sys
from pathlib import Path


def extract_section(changelog: str, tag: str) -> str:
    heading = f"## {tag}"
    lines = changelog.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration as exc:
        raise SystemExit(f"Changelog section not found: {heading}") from exc

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    section = "\n".join(lines[start:end]).strip() + "\n"
    if len(section.splitlines()) <= 1:
        raise SystemExit(f"Changelog section is empty: {heading}")
    return section


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: extract_release_notes.py CHANGELOG.md vX.Y.Z release-notes.md"
        )
    changelog_path, tag, output_path = map(Path, (sys.argv[1], sys.argv[2], sys.argv[3]))
    notes = extract_section(changelog_path.read_text(encoding="utf-8"), str(tag))
    Path(output_path).write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
