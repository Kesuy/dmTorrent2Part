from dmtorrent2part import __version__
from dmtorrent2part.gui import APP_TITLE


def test_gui_title_contains_package_version() -> None:
    assert APP_TITLE == f"dmTorrent2Part v{__version__} - Torrent → ED2K"
