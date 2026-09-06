from dmtorrent2part.ed2k import Ed2kLink
from dmtorrent2part.gui_multiselect import (
    contiguous_file_range,
    selected_file_indices,
    selection_link_lines,
)
from dmtorrent2part.torrent import TorrentFile


def test_selected_file_indices_filters_directories_and_sorts():
    assert selected_file_indices(("file:5", "dir:movies", "file:2", "root")) == (2, 5)


def test_contiguous_file_range_works_both_directions():
    visible = ("file:1", "file:2", "file:3", "file:4")
    assert contiguous_file_range(visible, "file:2", "file:4") == (
        "file:2",
        "file:3",
        "file:4",
    )
    assert contiguous_file_range(visible, "file:4", "file:2") == (
        "file:2",
        "file:3",
        "file:4",
    )


def test_selection_link_lines_is_one_uri_per_available_file():
    files = [
        TorrentFile(0, "A.mkv", 10, 0),
        TorrentFile(1, "B.mkv", 20, 10),
        TorrentFile(2, ".pad/0", 4, 30, is_pad=True),
        TorrentFile(3, "C.mkv", 30, 34),
    ]
    links = {
        0: Ed2kLink.from_hash("A.mkv", 10, bytes.fromhex("00" * 16)),
        3: Ed2kLink.from_hash("C.mkv", 30, bytes.fromhex("11" * 16)),
    }

    lines = selection_link_lines(files, links)
    assert len(lines) == 2
    assert lines[0].startswith("ed2k://|file|A.mkv|10|")
    assert lines[1].startswith("ed2k://|file|C.mkv|30|")
    assert "\n" not in lines[0]
    assert "\n" not in lines[1]
