from dmtorrent2part import __version__
from dmtorrent2part.gui import APP_TITLE


def test_gui_title_contains_package_version() -> None:
    assert __version__ == "1.1.3"
    assert APP_TITLE == "dmTorrent2Part v1.1.3 - Torrent → ED2K"
