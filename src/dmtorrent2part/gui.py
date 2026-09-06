from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .core import convert
from .ed2k import Ed2kLink, hash_file
from .icons import apply_window_icon
from .torrent import TorrentFile, TorrentMeta
from .torrent_repair import diagnose_torrent, format_diagnostic, repair_torrent

APP_TITLE = f"dmTorrent2Part v{__version__} - Torrent → ED2K"


class App(tk.Tk):
    def __init__(self, initial_torrent: str | None = None) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1020x700")
        self.minsize(860, 580)
        apply_window_icon(self)

        self.torrent: TorrentMeta | None = None
        self.links: dict[int, Ed2kLink] = {}
        self.file_iids: dict[int, str] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._busy = False

        self._build()
        self.after(100, self._poll)
        if initial_torrent:
            self.after(50, lambda: self._load_torrent(initial_torrent))

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)

        self.main_tab = ttk.Frame(self.notebook, padding=12)
        self.legacy_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.main_tab, text="Torrent → ED2K")
        self.notebook.add(self.legacy_tab, text="兼容：未完成文件 → Part")

        self._build_main(self.main_tab)
        self._build_legacy(self.legacy_tab)

    def _build_main(self, root: ttk.Frame) -> None:
        root.columnconfigure(1, weight=1)
        root.rowconfigure(4, weight=1)

        self.torrent_var = tk.StringVar()
        self.main_status_var = tk.StringVar(value="打开 torrent 后会按原目录结构列出全部文件")
        self.local_root_var = tk.StringVar()
        self.selected_var = tk.StringVar(value="未选择文件")
        self.source_var = tk.StringVar(value="")

        ttk.Label(root, text="Torrent 文件").grid(row=0, column=0, sticky="w")
        ttk.Entry(root, textvariable=self.torrent_var).grid(row=0, column=1, sticky="ew", padx=(8, 8))

        actions = ttk.Frame(root)
        actions.grid(row=0, column=2, sticky="e")
        ttk.Button(actions, text="打开 Torrent…", command=self._pick_torrent).pack(side="left")
        ttk.Button(actions, text="诊断", command=self._diagnose_current).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="修复 Torrent…", command=self._repair_current).pack(side="left", padx=(8, 0))

        ttk.Label(
            root,
            textvariable=self.main_status_var,
            foreground="#555",
            wraplength=900,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 8))

        hint = (
            "“诊断”用于检查非标准 torrent；“修复 Torrent”只清理文件头 BOM / 文件尾 CRLF、空白等附加字节，"
            "不会重编码 info 字典，因此不会改变 info hash。"
        )
        ttk.Label(root, text=hint, foreground="#666", wraplength=900).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        local = ttk.Frame(root)
        local.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        local.columnconfigure(1, weight=1)
        ttk.Label(local, text="本地下载根目录（可选）").grid(row=0, column=0, sticky="w")
        ttk.Entry(local, textvariable=self.local_root_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(local, text="选择目录…", command=self._pick_local_root).grid(row=0, column=2)
        self.batch_btn = ttk.Button(local, text="批量计算缺失 ED2K", command=self._batch_hash)
        self.batch_btn.grid(row=0, column=3, padx=(8, 0))

        paned = ttk.Panedwindow(root, orient="vertical")
        paned.grid(row=4, column=0, columnspan=3, sticky="nsew")

        tree_frame = ttk.Frame(paned)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("size", "status"),
            selectmode="browse",
        )
        self.tree.heading("#0", text="文件 / 目录")
        self.tree.heading("size", text="大小")
        self.tree.heading("status", text="ED2K")
        self.tree.column("#0", width=580, stretch=True)
        self.tree.column("size", width=115, anchor="e", stretch=False)
        self.tree.column("status", width=150, anchor="center", stretch=False)

        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        paned.add(tree_frame, weight=3)

        detail = ttk.LabelFrame(paned, text="选中文件", padding=10)
        detail.columnconfigure(0, weight=1)
        ttk.Label(detail, textvariable=self.selected_var).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(detail, textvariable=self.source_var, foreground="#555", wraplength=850).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(4, 6)
        )

        self.link_text = tk.Text(detail, height=3, wrap="word")
        self.link_text.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.link_text.configure(state="disabled")

        self.progress = ttk.Progressbar(detail, mode="determinate")
        self.progress.grid(row=3, column=0, sticky="ew", padx=(0, 12), pady=(8, 0))

        self.hash_btn = ttk.Button(
            detail,
            text="选择本地文件计算…",
            command=self._pick_selected_local,
            state="disabled",
        )
        self.hash_btn.grid(row=3, column=1, sticky="e", padx=(0, 8), pady=(8, 0))

        self.copy_btn = ttk.Button(
            detail,
            text="复制 ED2K",
            command=self._copy_link,
            state="disabled",
        )
        self.copy_btn.grid(row=3, column=2, sticky="e", pady=(8, 0))

        paned.add(detail, weight=1)

    def _build_legacy(self, root: ttk.Frame) -> None:
        root.columnconfigure(1, weight=1)
        root.rowconfigure(8, weight=1)

        self.legacy_torrent_var = tk.StringVar()
        self.incomplete_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd()))
        self.legacy_ed2k_var = tk.StringVar()
        self.part_var = tk.IntVar(value=1)
        self.met_only_var = tk.BooleanVar(value=False)
        self.legacy_status_var = tk.StringVar(value="保留 v1.0 的 BT 未完成文件 → eMule Part 功能")

        self._path_row(root, 0, "Torrent 文件", self.legacy_torrent_var, self._pick_legacy_torrent)

        ttk.Label(root, text="目标文件").grid(row=1, column=0, sticky="w", pady=5)
        self.legacy_combo = ttk.Combobox(root, state="readonly")
        self.legacy_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        self.legacy_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_legacy_ed2k())

        self._path_row(root, 2, "未完成文件", self.incomplete_var, self._pick_incomplete)
        self._path_row(root, 3, "输出目录", self.output_var, self._pick_output)

        ttk.Label(root, text="ED2K 链接").grid(row=4, column=0, sticky="nw", pady=5)
        ttk.Entry(root, textvariable=self.legacy_ed2k_var).grid(
            row=4, column=1, columnspan=2, sticky="ew", pady=5
        )

        opts = ttk.Frame(root)
        opts.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 8))
        ttk.Label(opts, text="Part 编号").pack(side="left")
        ttk.Spinbox(opts, from_=1, to=999, width=6, textvariable=self.part_var).pack(
            side="left", padx=(6, 18)
        )
        ttk.Checkbutton(opts, text="仅生成 .part.met", variable=self.met_only_var).pack(side="left")

        ttk.Label(
            root,
            text=(
                "该兼容功能依赖 BitTorrent v1 SHA-1 pieces；v2-only torrent 不能用于 Part 恢复，"
                "但仍可在第一个标签页生成 ED2K。"
            ),
            wraplength=800,
            foreground="#555",
        ).grid(row=6, column=0, columnspan=3, sticky="w")

        ttk.Label(root, textvariable=self.legacy_status_var).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=8
        )

        self.legacy_log = tk.Text(root, height=9, wrap="word", state="disabled")
        self.legacy_log.grid(row=8, column=0, columnspan=3, sticky="nsew")

        self.legacy_btn = ttk.Button(root, text="开始 Part 转换", command=self._start_legacy)
        self.legacy_btn.grid(row=9, column=2, sticky="e", pady=(8, 0))

    def _path_row(
        self,
        root: ttk.Frame,
        row: int,
        label: str,
        var: tk.StringVar,
        command,
    ) -> None:
        ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(root, textvariable=var).grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Button(root, text="浏览…", command=command).grid(
            row=row, column=2, padx=(8, 0), pady=5
        )

    def _pick_torrent(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Torrent", "*.torrent"), ("所有文件", "*.*")]
        )
        if path:
            self._load_torrent(path)

    def _pick_legacy_torrent(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Torrent", "*.torrent"), ("所有文件", "*.*")]
        )
        if path:
            self._load_torrent(path)
            self.notebook.select(self.legacy_tab)

    def _current_torrent_path(self) -> str | None:
        value = self.torrent_var.get().strip()
        if value and Path(value).is_file():
            return value
        path = filedialog.askopenfilename(
            title="选择 Torrent",
            filetypes=[("Torrent", "*.torrent"), ("所有文件", "*.*")],
        )
        return path or None

    def _diagnose_current(self) -> None:
        path = self._current_torrent_path()
        if not path:
            return
        try:
            result = diagnose_torrent(path)
        except Exception as exc:
            messagebox.showerror("Torrent 诊断失败", str(exc))
            return

        text = format_diagnostic(result)
        if result.valid_bencode and not result.has_issue:
            messagebox.showinfo("Torrent 诊断", text)
        elif result.recoverable:
            messagebox.showwarning("Torrent 诊断 - 可修复", text)
        else:
            messagebox.showerror("Torrent 诊断 - 异常", text)

    def _repair_current(self) -> None:
        path = self._current_torrent_path()
        if not path:
            return

        try:
            result = diagnose_torrent(path)
        except Exception as exc:
            messagebox.showerror("Torrent 修复失败", str(exc))
            return

        if not result.valid_bencode:
            messagebox.showerror("Torrent 无法修复", format_diagnostic(result))
            return
        if not result.has_issue:
            messagebox.showinfo("无需修复", "该 Torrent 格式正常，没有发现可清理的附加数据。")
            return
        if not result.recoverable:
            messagebox.showerror(
                "不建议自动修复",
                format_diagnostic(result) + "\n\n为避免误删有效数据，程序不会自动截断该文件。",
            )
            return

        source = Path(path)
        suggested = source.with_name(source.stem + ".fixed" + source.suffix)
        target = filedialog.asksaveasfilename(
            title="保存修复后的 Torrent",
            initialdir=str(source.parent),
            initialfile=suggested.name,
            defaultextension=".torrent",
            filetypes=[("Torrent", "*.torrent"), ("所有文件", "*.*")],
        )
        if not target:
            return

        try:
            fixed = repair_torrent(source, target)
            TorrentMeta.from_file(fixed)
        except Exception as exc:
            messagebox.showerror("Torrent 修复失败", str(exc))
            return

        messagebox.showinfo(
            "Torrent 修复完成",
            f"已生成：\n{fixed}\n\n只移除了额外的 BOM / 尾部空白，bencode 主体保持原始字节不变。",
        )
        self._load_torrent(str(fixed))

    def _load_torrent(self, path: str) -> None:
        try:
            torrent = TorrentMeta.from_file(path)
        except Exception as exc:
            try:
                diagnostic = diagnose_torrent(path)
                detail = format_diagnostic(diagnostic)
            except Exception:
                diagnostic = None
                detail = str(exc)

            if diagnostic and diagnostic.recoverable:
                repair_now = messagebox.askyesno(
                    "Torrent 读取失败 - 可修复",
                    f"{detail}\n\n是否立即导出修复后的 Torrent？",
                )
                if repair_now:
                    self.torrent_var.set(path)
                    self._repair_current()
                return

            messagebox.showerror("Torrent 读取失败", f"{exc}\n\n{detail}")
            return

        self.torrent = torrent
        self.links.clear()
        for file in torrent.files:
            if file.ed2k_hash:
                self.links[file.index] = Ed2kLink.from_hash(
                    file.name, file.length, file.ed2k_hash
                )

        self.torrent_var.set(path)
        self.legacy_torrent_var.set(path)
        self._populate_tree()

        values = [
            f"[{f.index}] {f.path}  ({_human(f.length)})"
            for f in torrent.files
            if not f.is_pad
        ]
        self.legacy_combo["values"] = values
        if values:
            self.legacy_combo.current(0)
            self._sync_legacy_ed2k()

        embedded = sum(1 for f in torrent.files if f.ed2k_hash and not f.is_pad)
        kind = (
            "Hybrid"
            if torrent.is_hybrid
            else ("BitTorrent v2" if torrent.meta_version == 2 else "BitTorrent v1")
        )
        text = f"{kind} · {len(torrent.files)} 个文件 · torrent 内置 ED2K：{embedded} 个"

        try:
            diagnostic = diagnose_torrent(path)
        except Exception:
            diagnostic = None
        if diagnostic and diagnostic.recoverable and diagnostic.has_issue:
            text += f" · ⚠ 已兼容非标准 Torrent：{diagnostic.message}"
        elif torrent.warning:
            text += f" · {torrent.warning}"

        self.main_status_var.set(text)
        self.legacy_status_var.set(
            "可进行 Part 转换"
            if torrent.v1_compatible
            else "该 torrent 仅可用于 Torrent → ED2K；不能进行 Part 转换"
        )

    def _populate_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.file_iids.clear()
        if not self.torrent:
            return

        torrent = self.torrent
        files = list(torrent.files)
        common_root = None

        if len(files) > 1:
            first_parts = [
                f.path.replace("\\", "/").split("/")[0]
                for f in files
                if f.path
            ]
            if not first_parts or not all(p == torrent.name for p in first_parts):
                common_root = self.tree.insert(
                    "", "end", iid="root", text=torrent.name, open=True
                )

        folders: dict[tuple[str, ...], str] = {}
        for file in files:
            parts = [p for p in file.path.replace("\\", "/").split("/") if p]
            parent = common_root or ""
            prefix: list[str] = []

            for part in parts[:-1]:
                prefix.append(part)
                key = tuple(prefix)
                if key not in folders:
                    iid = "dir:" + "/".join(prefix)
                    folders[key] = iid
                    self.tree.insert(parent, "end", iid=iid, text=part, open=True)
                parent = folders[key]

            iid = f"file:{file.index}"
            self.file_iids[file.index] = iid
            self.tree.insert(
                parent,
                "end",
                iid=iid,
                text=parts[-1] if parts else file.name,
                values=(_human(file.length), self._status(file)),
            )

    def _status(self, file: TorrentFile) -> str:
        if file.is_pad:
            return "填充文件"
        if file.index in self.links:
            return "已有 ED2K"
        if self._resolve_local(file):
            return "可计算"
        return "需本地文件"

    def _selected_file(self) -> TorrentFile | None:
        if not self.torrent:
            return None
        selection = self.tree.selection()
        if not selection or not selection[0].startswith("file:"):
            return None
        return self.torrent.files[int(selection[0].split(":", 1)[1])]

    def _on_tree_select(self, _event=None) -> None:
        target = self._selected_file()
        if target is None:
            return

        self.selected_var.set(f"{target.path}    {_human(target.length)}")

        if target.is_pad:
            self.source_var.set("这是 torrent 的 padding 文件，不生成 ED2K 链接。")
            self._set_link_text("")
            self.copy_btn.configure(state="disabled")
            self.hash_btn.configure(state="disabled")
            return

        link = self.links.get(target.index)
        if link:
            source = "torrent 内置 ED2K" if target.ed2k_hash else "从本地文件计算"
            self.source_var.set(source)
            self._set_link_text(link.to_uri())
            self.copy_btn.configure(state="normal")
        else:
            local = self._resolve_local(target)
            self.source_var.set(
                "torrent 未包含 ED2K；请选择完整本地文件计算。"
                + (f" 已匹配：{local}" if local else "")
            )
            self._set_link_text("")
            self.copy_btn.configure(state="disabled")

        self.hash_btn.configure(state="normal")
        self._sync_legacy_ed2k(target.index)

    def _set_link_text(self, text: str) -> None:
        self.link_text.configure(state="normal")
        self.link_text.delete("1.0", "end")
        self.link_text.insert("1.0", text)
        self.link_text.configure(state="disabled")

    def _copy_link(self) -> None:
        target = self._selected_file()
        if not target or target.index not in self.links:
            return
        text = self.links[target.index].to_uri()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.main_status_var.set("ED2K 链接已复制到剪贴板")

    def _pick_local_root(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.local_root_var.set(path)
            self._refresh_statuses()
            self._on_tree_select()

    def _resolve_local(self, target: TorrentFile) -> Path | None:
        if not self.torrent or not self.local_root_var.get():
            return None

        root = Path(self.local_root_var.get())
        rel = Path(*[p for p in target.path.replace("\\", "/").split("/") if p])
        candidates = [root / rel, root / self.torrent.name / rel]
        if len(self.torrent.files) == 1:
            candidates.insert(0, root / target.name)

        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stat().st_size == target.length:
                    return candidate
            except OSError:
                continue
        return None

    def _pick_selected_local(self) -> None:
        target = self._selected_file()
        if not target:
            return

        initialdir = self.local_root_var.get() or str(Path.cwd())
        path = filedialog.askopenfilename(
            initialdir=initialdir,
            initialfile=target.name,
            filetypes=[("所有文件", "*.*")],
        )
        if not path:
            return

        local = Path(path)
        try:
            actual = local.stat().st_size
        except OSError as exc:
            messagebox.showerror("读取失败", str(exc))
            return

        if actual != target.length:
            messagebox.showerror(
                "文件不匹配",
                f"文件大小不一致：本地 {actual} 字节，torrent {target.length} 字节。",
            )
            return

        self._start_hash([(target, local)])

    def _batch_hash(self) -> None:
        if not self.torrent:
            messagebox.showinfo("提示", "请先打开 torrent。")
            return

        if not self.local_root_var.get():
            self._pick_local_root()
            if not self.local_root_var.get():
                return

        jobs: list[tuple[TorrentFile, Path]] = []
        for target in self.torrent.files:
            if target.is_pad or target.index in self.links:
                continue
            local = self._resolve_local(target)
            if local:
                jobs.append((target, local))

        if not jobs:
            messagebox.showinfo(
                "没有可计算文件",
                "没有找到大小匹配、且缺少 ED2K 的本地文件。",
            )
            return

        self._start_hash(jobs)

    def _start_hash(self, jobs: list[tuple[TorrentFile, Path]]) -> None:
        if self._busy:
            return

        self._busy = True
        self.hash_btn.configure(state="disabled")
        self.batch_btn.configure(state="disabled")
        self.progress["value"] = 0

        def worker() -> None:
            try:
                for number, (target, local) in enumerate(jobs, start=1):
                    self.events.put(
                        ("hash_status", f"正在计算 {number}/{len(jobs)}：{target.path}")
                    )
                    link = hash_file(
                        local,
                        display_name=target.name,
                        progress=lambda done, total, idx=target.index: self.events.put(
                            ("hash_progress", (idx, done, total))
                        ),
                    )
                    if link.size != target.length:
                        raise ValueError(f"文件大小在计算过程中发生变化：{target.path}")
                    self.events.put(("hash_one", (target.index, link)))
                self.events.put(("hash_done", len(jobs)))
            except Exception as exc:
                self.events.put(("hash_error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_statuses(self) -> None:
        if not self.torrent:
            return
        for file in self.torrent.files:
            iid = self.file_iids.get(file.index)
            if iid and self.tree.exists(iid):
                self.tree.set(iid, "status", self._status(file))

    def _pick_incomplete(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("所有文件", "*.*")])
        if path:
            self.incomplete_var.set(path)

    def _pick_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

    def _legacy_target(self) -> TorrentFile | None:
        if not self.torrent:
            return None
        non_pad = [f for f in self.torrent.files if not f.is_pad]
        index = self.legacy_combo.current()
        return non_pad[index] if 0 <= index < len(non_pad) else None

    def _sync_legacy_ed2k(self, preferred_index: int | None = None) -> None:
        target = None
        if preferred_index is not None and self.torrent:
            target = next(
                (
                    f
                    for f in self.torrent.files
                    if f.index == preferred_index and not f.is_pad
                ),
                None,
            )
            if target:
                non_pad = [f for f in self.torrent.files if not f.is_pad]
                try:
                    self.legacy_combo.current(non_pad.index(target))
                except ValueError:
                    pass

        target = target or self._legacy_target()
        if target and target.index in self.links:
            self.legacy_ed2k_var.set(self.links[target.index].to_uri())

    def _start_legacy(self) -> None:
        try:
            if not self.torrent:
                raise ValueError("请选择 torrent 文件")

            target = self._legacy_target()
            if target is None:
                raise ValueError("请选择 torrent 内目标文件")

            if not self.torrent.v1_compatible:
                raise ValueError(
                    "该 torrent 没有有效的 BitTorrent v1 SHA-1 pieces，不能执行 Part 转换。"
                )

            ed2k = Ed2kLink.parse(self.legacy_ed2k_var.get())
            incomplete = Path(self.incomplete_var.get())
            if not incomplete.is_file():
                raise ValueError("请选择有效的未完成文件")

            output = Path(self.output_var.get())
            part_number = int(self.part_var.get())
            met_only = self.met_only_var.get()
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self.legacy_btn.configure(state="disabled")
        self.legacy_status_var.set("正在校验 BT v1 分片…")

        def worker() -> None:
            try:
                result = convert(
                    self.torrent,
                    target,
                    incomplete,
                    ed2k,
                    output,
                    part_number=part_number,
                    met_only=met_only,
                )
                self.events.put(("legacy_done", result))
            except Exception as exc:
                self.events.put(("legacy_error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _legacy_log_line(self, text: str) -> None:
        self.legacy_log.configure(state="normal")
        self.legacy_log.insert("end", text + "\n")
        self.legacy_log.see("end")
        self.legacy_log.configure(state="disabled")

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()

                if kind == "hash_status":
                    self.main_status_var.set(str(payload))

                elif kind == "hash_progress":
                    _idx, done, total = payload
                    self.progress["maximum"] = max(1, total)
                    self.progress["value"] = done

                elif kind == "hash_one":
                    index, link = payload
                    self.links[index] = link
                    self._refresh_statuses()
                    target = self._selected_file()
                    if target and target.index == index:
                        self._on_tree_select()

                elif kind == "hash_done":
                    self._busy = False
                    self.hash_btn.configure(
                        state="normal" if self._selected_file() else "disabled"
                    )
                    self.batch_btn.configure(state="normal")
                    self.progress["value"] = 0
                    self.main_status_var.set(f"ED2K 计算完成：{payload} 个文件")

                elif kind == "hash_error":
                    self._busy = False
                    self.hash_btn.configure(
                        state="normal" if self._selected_file() else "disabled"
                    )
                    self.batch_btn.configure(state="normal")
                    self.main_status_var.set("ED2K 计算失败")
                    messagebox.showerror("计算失败", str(payload))

                elif kind == "legacy_done":
                    result = payload
                    verification = result.verification
                    self._legacy_log_line(
                        f"验证通过：{_human(verification.verified_bytes)}；"
                        f"匹配分片 {verification.matched_pieces}/{verification.checked_pieces}"
                    )
                    self._legacy_log_line(f"MET：{result.met_path}")
                    if result.part_path:
                        self._legacy_log_line(f"PART：{result.part_path}")
                    self.legacy_status_var.set("Part 转换完成")
                    self.legacy_btn.configure(state="normal")
                    messagebox.showinfo("完成", "Part 转换完成。")

                elif kind == "legacy_error":
                    self.legacy_status_var.set("Part 转换失败")
                    self.legacy_btn.configure(state="normal")
                    messagebox.showerror("转换失败", str(payload))
        except queue.Empty:
            pass

        self.after(100, self._poll)


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def main() -> None:
    initial = None
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".torrent"):
        initial = sys.argv[1]
    App(initial).mainloop()
