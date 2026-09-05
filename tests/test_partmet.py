from dmtorrent2part.partmet import (
    FT_FILESIZE,
    FT_FILENAME,
    FT_GAPEND,
    FT_GAPSTART,
    PartMetInfo,
    read_part_met,
    write_part_met,
)


def test_partmet_structure_and_gap_tags(tmp_path):
    path = tmp_path / "001.part.met"
    info = PartMetInfo(
        filename="测试.bin",
        file_size=100,
        file_hash=bytes.fromhex("00" * 16),
        part_hashes=(),
        gaps=((10, 19), (50, 99)),
        transferred=40,
    )
    write_part_met(path, info, timestamp=123)
    parsed = read_part_met(path)
    assert parsed["version"] == 0xE0
    tags = parsed["tags"]
    assert any(name == bytes([FT_FILENAME]) and value == "测试.bin" for _, name, value in tags)
    assert any(name == bytes([FT_FILESIZE]) and value == 100 for _, name, value in tags)
    assert any(name == bytes([FT_GAPSTART]) + b"0" and value == 10 for _, name, value in tags)
    assert any(name == bytes([FT_GAPEND]) + b"0" and value == 20 for _, name, value in tags)
