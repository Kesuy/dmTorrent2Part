from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import convert
from .ed2k import Ed2kLink
from .torrent import TorrentMeta


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("dmTorrent2Part")
        self.geometry("780x560")
        self.minsize(720, 500)
        self.torrent: TorrentMeta | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._build()
        self.after(100, self._poll)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        self.torrent_var = tk.StringVar()
        self.incomplete_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd()))
        self.ed2k_var = tk.StringVar()
        self.part_var = tk.IntVar(value=1)
        self.met_only_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择 torrent 文件")

        self._path_row(root, 0, "Torrent 文件", self.torrent_var, self._pick_torrent)
        ttk.Label(root, text="目标文件").grid(row=1, column=0, sticky="w", pady=5)
        self.file_combo = ttk.Combobox(root, state="readonly")
        self.file_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)

        self._path_row(root, 2, "未完成文件", self.incomplete_var, self._pick_incomplete)
        self._path_row(root, 3, "输出目录", self.output_var, self._pick_output, folder=True)

        ttk.Label(root, text="ED2K 链接").grid(row=4, column=0, sticky="nw", pady=5)
        ed = ttk.Entry(root, textvariable=self.ed2k_var)
        ed.grid(row=4, column=1, columnspan=2, sticky="ew", pady=5)

        opts = ttk.Frame(root)
        opts.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 8))
        ttk.Label(opts, text="Part 编号").pack(side="left")
        ttk.Spinbox(opts, from_=1, to=999, width=6, textvariable=self.part_var).pack(side="left", padx=(6, 18))
        ttk.Checkbutton(opts, text="仅生成 .part.met", variable=self.met_only_var).pack(side="left")

        info = (
            "程序只把 SHA-1 校验通过的 BT 分片写入 .part；未验证、损坏以及多文件种子的跨文件边界分片会标记为缺口，"
            "交给 eMule 重新下载。"
        )
        ttk.Label(root, text=info, wraplength=720, foreground="#555").grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(root, textvariable=self.status_var).grid(row=8, column=0, columnspan=3, sticky="w", pady=5)

        self.log = tk.Text(root, height=12, wrap="word", state="disabled")
        self.log.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=(6, 8))
        root.rowconfigure(9, weight=1)

        self.run_btn = ttk.Button(root, text="开始转换", command=self._start)
        self.run_btn.grid(row=10, column=2, sticky="e")

    def _path_row(self, root: ttk.Frame, row: int, label: str, var: tk.StringVar, command, folder: bool = False) -> None:
        ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(root, textvariable=var).grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Button(root, text="浏览…", command=command).grid(row=row, column=2, padx=(8, 0), pady=5)

    def _pick_torrent(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Torrent", "*.torrent"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            torrent = TorrentMeta.from_file(path)
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))
            return
        self.torrent = torrent
        self.torrent_var.set(path)
        values = [f"[{f.index}] {f.path}  ({_human(f.length)})" for f in torrent.files]
        self.file_combo["values"] = values
        if values:
            self.file_combo.current(0)
        self.status_var.set(f"已载入：{torrent.name}，{len(values)} 个文件")

    def _pick_incomplete(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("所有文件", "*.*")])
        if path:
            self.incomplete_var.set(path)

    def _pick_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

    def _start(self) -> None:
        try:
            torrent = self.torrent or TorrentMeta.from_file(self.torrent_var.get())
            index = self.file_combo.current()
            if index < 0:
                raise ValueError("请选择 torrent 内的目标文件")
            target = torrent.files[index]
            ed2k = Ed2kLink.parse(self.ed2k_var.get())
            incomplete = Path(self.incomplete_var.get())
            output = Path(self.output_var.get())
            part_number = int(self.part_var.get())
            if not incomplete.is_file():
                raise ValueError("请选择有效的未完成文件")
            if self.met_only_var.get():
                ok = messagebox.askyesno(
                    "仅生成 MET",
                    f"将只生成 {part_number:03d}.part.met，不创建 {part_number:03d}.part。\n"
                    "请确保对应 .part 文件会由你自行放入 eMule 临时目录。继续吗？",
                )
                if not ok:
                    return
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self.run_btn.configure(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("正在校验 BT 分片…")
        self._log("开始校验；只保留 SHA-1 验证通过的数据。")

        def worker() -> None:
            try:
                result = convert(
                    torrent,
                    target,
                    incomplete,
                    ed2k,
                    output,
                    part_number=part_number,
                    met_only=self.met_only_var.get(),
                    progress=lambda done, total: self.events.put(("progress", (done, total))),
                )
                self.events.put(("done", result))
            except Exception as exc:
                self.events.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    done, total = payload
                    self.progress["maximum"] = max(1, total)
                    self.progress["value"] = done
                    self.status_var.set(f"正在校验分片：{done}/{total}")
                elif kind == "done":
                    result = payload
                    v = result.verification
                    self._log(f"验证通过：{_human(v.verified_bytes)}；匹配分片 {v.matched_pieces}/{v.checked_pieces}")
                    self._log(f"MET：{result.met_path}")
                    if result.part_path:
                        self._log(f"PART：{result.part_path}")
                    if v.skipped_boundary_bytes:
                        self._log(f"跨文件边界无法单独验证：{_human(v.skipped_boundary_bytes)}，已标记为缺口。")
                    self.status_var.set("转换完成")
                    self.run_btn.configure(state="normal")
                    messagebox.showinfo("完成", "转换完成。将 .part 和 .part.met 放入 eMule 临时目录后重启/重新扫描即可。")
                elif kind == "error":
                    self.status_var.set("转换失败")
                    self.run_btn.configure(state="normal")
                    messagebox.showerror("转换失败", str(payload))
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def main() -> None:
    App().mainloop()
