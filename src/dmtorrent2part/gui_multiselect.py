from __future__ import annotations

import sys
import tkinter as tk
from collections.abc import Iterable, Mapping, Sequence
from tkinter import messagebox, ttk

from .ed2k import Ed2kLink
from .gui import App as BaseApp, _human
from .torrent import TorrentFile

_SHIFT_MASK = 0x0001
_CONTROL_MASK = 0x0004
_MODIFIER_MASK = _SHIFT_MASK | _CONTROL_MASK


def selected_file_indices(iids: Iterable[str]) -> tuple[int, ...]:
    """Return selected torrent file indexes in torrent/display order."""
    indexes: set[int] = set()
    for iid in iids:
        if not iid.startswith("file:"):
            continue
        try:
            indexes.add(int(iid.split(":", 1)[1]))
        except ValueError:
            continue
    return tuple(sorted(indexes))


def selection_link_lines(
    files: Sequence[TorrentFile], links: Mapping[int, Ed2kLink]
) -> tuple[str, ...]:
    """Return one ED2K URI per selected non-padding file that has a link."""
    return tuple(
        links[file.index].to_uri()
        for file in files
        if not file.is_pad and file.index in links
    )


def contiguous_file_range(
    visible_file_iids: Sequence[str], anchor: str, target: str
) -> tuple[str, ...]:
    """Return the inclusive visible file range used by mouse-drag selection."""
    try:
        left = visible_file_iids.index(anchor)
        right = visible_file_iids.index(target)
    except ValueError:
        return ()
    if left > right:
        left, right = right, left
    return tuple(visible_file_iids[left : right + 1])


class App(BaseApp):
    """GUI variant with Windows-style multi-selection for torrent files."""

    def __init__(self, initial_torrent: str | None = None) -> None:
        self._drag_anchor: str | None = None
        super().__init__(initial_torrent)

    def _build_main(self, root: ttk.Frame) -> None:
        super()._build_main(root)

        # extended enables native Ctrl-toggle and Shift-range selection.
        self.tree.configure(selectmode="extended")
        self.tree.bind("<ButtonPress-1>", self._remember_drag_anchor, add="+")
        self.tree.bind("<B1-Motion>", self._drag_select, add="+")

        # Multi-selection can produce many links, so give the ED2K area more room
        # and make every URI occupy exactly one visual/text line.
        self.link_text.configure(height=8, wrap="none")
        detail = self.link_text.master
        link_scroll = ttk.Scrollbar(detail, orient="vertical", command=self.link_text.yview)
        link_scroll.grid(row=2, column=3, sticky="ns")
        self.link_text.configure(yscrollcommand=link_scroll.set)
        self.copy_btn.configure(text="复制所选 ED2K")

    def _selected_files(self) -> list[TorrentFile]:
        if not self.torrent:
            return []
        indexes = selected_file_indices(self.tree.selection())
        by_index = {file.index: file for file in self.torrent.files}
        return [by_index[index] for index in indexes if index in by_index]

    def _selected_file(self) -> TorrentFile | None:
        files = self._selected_files()
        return files[0] if len(files) == 1 else None

    def _on_tree_select(self, _event=None) -> None:
        files = self._selected_files()
        if not files:
            self.selected_var.set("未选择文件")
            self.source_var.set("可使用鼠标拖选、Ctrl 或 Shift 选择多个文件。")
            self._set_link_text("")
            self.copy_btn.configure(text="复制所选 ED2K", state="disabled")
            self.hash_btn.configure(state="disabled")
            return

        if len(files) == 1:
            self.copy_btn.configure(text="复制 ED2K")
            super()._on_tree_select(_event)
            return

        real_files = [file for file in files if not file.is_pad]
        lines = selection_link_lines(real_files, self.links)
        missing = sum(1 for file in real_files if file.index not in self.links)
        pads = len(files) - len(real_files)
        total_size = sum(file.length for file in real_files)

        self.selected_var.set(
            f"已选择 {len(real_files)} 个文件 · 合计 {_human(total_size)}"
            + (f" · 忽略 {pads} 个 padding 文件" if pads else "")
        )

        summary = f"可用 ED2K：{len(lines)} 条"
        if missing:
            summary += f" · 缺失 ED2K：{missing} 个（可用本地下载根目录批量计算）"
        self.source_var.set(summary)
        self._set_link_text("\n".join(lines))

        if lines:
            self.copy_btn.configure(text=f"复制 {len(lines)} 条 ED2K", state="normal")
        else:
            self.copy_btn.configure(text="复制所选 ED2K", state="disabled")

        # A single file chooser cannot safely map multiple torrent entries.
        # Existing root-directory batch calculation remains available above.
        self.hash_btn.configure(state="disabled")

    def _copy_link(self) -> None:
        files = self._selected_files()
        lines = selection_link_lines(files, self.links)
        if not lines:
            return
        text = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.main_status_var.set(f"已复制 {len(lines)} 条 ED2K 链接到剪贴板")

    def _pick_selected_local(self) -> None:
        files = self._selected_files()
        if len(files) != 1:
            if files:
                messagebox.showinfo(
                    "多选文件",
                    "多选时请先设置“本地下载根目录”，再使用“批量计算缺失 ED2K”。",
                )
            return
        super()._pick_selected_local()

    def _refresh_statuses(self) -> None:
        super()._refresh_statuses()
        if self.tree.selection():
            self._on_tree_select()

    def _remember_drag_anchor(self, event: tk.Event) -> None:
        if event.state & _MODIFIER_MASK:
            return
        iid = self.tree.identify_row(event.y)
        self._drag_anchor = iid if iid.startswith("file:") else None

    def _visible_file_iids(self) -> list[str]:
        visible: list[str] = []

        def walk(parent: str) -> None:
            for iid in self.tree.get_children(parent):
                if iid.startswith("file:"):
                    visible.append(iid)
                elif bool(self.tree.item(iid, "open")):
                    walk(iid)

        walk("")
        return visible

    def _drag_select(self, event: tk.Event):
        if event.state & _MODIFIER_MASK or not self._drag_anchor:
            return None
        target = self.tree.identify_row(event.y)
        if not target.startswith("file:"):
            return None

        selection = contiguous_file_range(
            self._visible_file_iids(), self._drag_anchor, target
        )
        if not selection:
            return None

        self.tree.selection_set(selection)
        self.tree.focus(target)
        self.tree.see(target)
        return "break"


def main() -> None:
    initial = None
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".torrent"):
        initial = sys.argv[1]
    App(initial).mainloop()
