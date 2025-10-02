from __future__ import annotations

import os
import sys
import math
import time
import threading
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- Theme ----
try:
    import ttkbootstrap as ttkb
    from ttkbootstrap.constants import *
    from ttkbootstrap.dialogs import Messagebox
    TKMOD = "ttkbootstrap"
except Exception:
    ttkb = None
    TKMOD = "tk"

import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import messagebox as tk_messagebox

# ---- Imaging / hashing / safe delete ----
from PIL import Image, ImageFile, ImageTk, ImageOps
ImageFile.LOAD_TRUNCATED_IMAGES = True

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

try:
    import imagehash
except Exception as e:
    raise SystemExit("Missing dependency: imagehash. Install with `pip install imagehash pillow`.") from e

try:
    from send2trash import send2trash
except Exception:
    send2trash = None  

# ---------- Config ----------
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff",
    ".webp", ".jfif", ".pjpeg", ".pjp", ".avif", ".heic", ".heif"
}
DEFAULT_HASH_ALGO = "phash"   # 'ahash','dhash','phash','whash','colorhash'
DEFAULT_HASH_SIZE = 16
DEFAULT_THRESHOLD = 5
BUCKET_PREFIX_HEX_CHARS = 4

# ---------- Data ----------
@dataclass
class ImageRecord:
    path: Path
    size_bytes: int
    mtime: float
    width: int
    height: int
    hash_str: str
    group_id: Optional[int] = None
    marked_for_delete: bool = False

    @property
    def resolution_str(self) -> str:
        return f"{self.width}×{self.height}"

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

# ---------- Hashing ----------
class HashEngine:
    def __init__(self, algo: str = DEFAULT_HASH_ALGO, hash_size: int = DEFAULT_HASH_SIZE):
        self.algo = algo.lower()
        self.hash_size = hash_size

    def compute(self, img: Image.Image) -> str:
        a = self.algo
        if a == "ahash":
            h = imagehash.average_hash(img, hash_size=self.hash_size)
        elif a == "dhash":
            h = imagehash.dhash(img, hash_size=self.hash_size)
        elif a == "phash":
            h = imagehash.phash(img, hash_size=self.hash_size)
        elif a == "whash":
            h = imagehash.whash(img, hash_size=self.hash_size)
        elif a == "colorhash":
            binbits = max(3, min(8, int(round(math.log2(self.hash_size)))))
            h = imagehash.colorhash(img, binbits=binbits)
        else:
            h = imagehash.phash(img, hash_size=self.hash_size)
        return str(h)

    @staticmethod
    def hamming_distance(h1: str, h2: str) -> int:
        return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)

# ---------- Grouping ----------
class DupeGrouper:
    def __init__(self, threshold: int, bucket_hex_chars: int = BUCKET_PREFIX_HEX_CHARS):
        self.threshold = max(0, threshold)
        self.bucket_hex_chars = max(1, bucket_hex_chars)

    def build_groups(self, records: List[ImageRecord]) -> Dict[int, List[int]]:
        buckets: Dict[str, List[int]] = {}
        for idx, rec in enumerate(records):
            buckets.setdefault(rec.hash_str[:self.bucket_hex_chars], []).append(idx)

        parent = list(range(len(records)))
        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        def union(a: int, b: int):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for _, idxs in buckets.items():
            n = len(idxs)
            if n < 2:
                continue
            for i in range(n - 1):
                ri = records[idxs[i]]
                hi = ri.hash_str
                for j in range(i + 1, n):
                    rj = records[idxs[j]]
                    if hi == rj.hash_str:
                        union(idxs[i], idxs[j])
                    else:
                        d = HashEngine.hamming_distance(hi, rj.hash_str)
                        if d <= self.threshold:
                            union(idxs[i], idxs[j])

        groups: Dict[int, List[int]] = {}
        for idx in range(len(records)):
            root = find(idx)
            groups.setdefault(root, []).append(idx)
        return {gid: m for gid, m in groups.items() if len(m) > 1}

# ---------- Scanning ----------
class ImageScanner:
    def __init__(self, engine: HashEngine, stop_event: threading.Event):
        self.engine = engine
        self.stop_event = stop_event

    def scan_folder(self, root: Path, progress_cb=None) -> List[ImageRecord]:
        files = self._collect_files(root)
        total = len(files)
        records: List[ImageRecord] = []
        workers = max(4, (os.cpu_count() or 4))

        def update(i):
            if progress_cb:
                progress_cb(i, total)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(self._hash_one, fpath) for fpath in files]
            for i, fut in enumerate(as_completed(futures), 1):
                if self.stop_event.is_set():
                    break
                rec = fut.result()
                if rec:
                    records.append(rec)
                update(i)
        return records

    def _collect_files(self, root: Path) -> List[Path]:
        out: List[Path] = []
        for dp, _, fns in os.walk(root):
            if self.stop_event.is_set():
                break
            for n in fns:
                if Path(n).suffix.lower() in IMAGE_EXTS:
                    out.append(Path(dp) / n)
        return out

    def _hash_one(self, path: Path) -> Optional[ImageRecord]:
        try:
            st = path.stat()
            with Image.open(path) as im:
                try:
                    im.seek(0) 
                except Exception:
                    pass
                im = ImageOps.exif_transpose(im) 
                width, height = im.size
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                h = self.engine.compute(im)
            return ImageRecord(
                path=path, size_bytes=st.st_size, mtime=st.st_mtime,
                width=width, height=height, hash_str=h
            )
        except Exception:
            return None

# ---------- App ----------
class DuplicateFinderApp:
    def __init__(self):
        self.stop_event = threading.Event()
        self.engine = HashEngine()
        self.records: List[ImageRecord] = []
        self.groups: Dict[int, List[int]] = {}
        self.current_folder: Optional[Path] = None

        # Preview state/cache
        self._preview_pil: Optional[Image.Image] = None
        self._preview_photo: Optional[ImageTk.PhotoImage] = None
        self._preview_path: Optional[Path] = None

        # Tree row mapping: iid -> record index
        self._iid_to_index: Dict[str, int] = {}

        if ttkb:
            self.root = ttkb.Window(themename="darkly")
            self.StyleMsg = Messagebox
        else:
            self.root = tk.Tk()
            self.StyleMsg = None
            try:
                ttk.Style().theme_use("clam")
            except Exception:
                pass

        self.root.title("Image Duplicate Finder")
        self.root.geometry("1200x720")
        self.root.minsize(960, 600)
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        self.folder_var = tk.StringVar(value="")
        self.algo_var = tk.StringVar(value=DEFAULT_HASH_ALGO)
        self.hash_size_var = tk.IntVar(value=DEFAULT_HASH_SIZE)
        self.threshold_var = tk.IntVar(value=DEFAULT_THRESHOLD)
        self.status_var = tk.StringVar(value="Select a folder and click Scan")

        ttk.Button(top, text="📂 Select Folder", command=self.on_pick_folder).pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.folder_var, width=60).pack(side=tk.LEFT, padx=8)

        ttk.Label(top, text="Algorithm").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Combobox(top, textvariable=self.algo_var, state="readonly",
                     values=["phash", "dhash", "ahash", "whash", "colorhash"], width=10).pack(side=tk.LEFT)

        ttk.Label(top, text="Hash size").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Spinbox(top, from_=8, to=32, textvariable=self.hash_size_var, width=5).pack(side=tk.LEFT)

        ttk.Label(top, text="Threshold").pack(side=tk.LEFT, padx=(12, 4))
        self.thres_scale = ttk.Scale(top, from_=0, to=20, orient=tk.HORIZONTAL,
                                     variable=self.threshold_var, length=160)
        self.thres_scale.pack(side=tk.LEFT)

        self.scan_btn = ttk.Button(top, text="▶ Scan", command=self.on_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=(12, 4))
        self.cancel_btn = ttk.Button(top, text="⏹ Cancel", command=self.on_cancel, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT)

        self.pvar = tk.DoubleVar(value=0.0)
        self.pbar = ttk.Progressbar(top, variable=self.pvar, maximum=1.0, length=200, mode="determinate")
        self.pbar.pack(side=tk.RIGHT, padx=4)

        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(main)
        self.tree = ttk.Treeview(
            left,
            columns=("select", "filename", "resolution", "size", "path"),
            show="tree headings", 
            selectmode="extended"
        )
        # Headings
        self.tree.heading("#0", text="Group")
        self.tree.heading("select", text="Select")
        self.tree.heading("filename", text="Filename")
        self.tree.heading("resolution", text="Resolution")
        self.tree.heading("size", text="Size (MB)")
        self.tree.heading("path", text="Path")

        # Column widths / stretch
        self.tree.column("#0", width=180, stretch=True)
        self.tree.column("select", width=70, stretch=False, anchor="center")
        self.tree.column("filename", width=260, stretch=True)
        self.tree.column("resolution", width=110, stretch=False)
        self.tree.column("size", width=90, stretch=False, anchor="e")
        self.tree.column("path", width=420, stretch=True)

        yscroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(left, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(main, padding=(10, 0, 0, 0))
        ttk.Label(right, text="Preview").pack(anchor="w")
        self.preview_canvas = tk.Canvas(right, highlightthickness=0, bg="#111", height=320)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<Configure>", self._on_preview_resize)

        acts = ttk.Frame(right)
        acts.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(acts, text="Select all NON-best per group", command=self.on_select_non_best).pack(fill=tk.X, pady=2)
        ttk.Button(acts, text="Toggle select for chosen rows", command=self.on_toggle_mark_selected).pack(fill=tk.X, pady=2)
        ttk.Button(acts, text="Open containing folder", command=self.on_open_folder).pack(fill=tk.X, pady=2)
        ttk.Button(acts, text="Export CSV report…", command=self.on_export_csv).pack(fill=tk.X, pady=2)

        del_text = "Delete selected to Recycle Bin" if send2trash else "Permanently delete selected"
        self.delete_btn = ttk.Button(right, text=del_text, command=self.on_delete_marked,
                                     bootstyle="danger" if ttkb else None)
        self.delete_btn.pack(fill=tk.X, pady=(12, 2))

        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status.pack(fill=tk.X, pady=(0, 6), padx=10)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        main.add(left, weight=3)
        main.add(right, weight=2)

    # ---------- Events ----------
    def on_pick_folder(self):
        folder = filedialog.askdirectory(title="Choose image folder")
        if folder:
            self.folder_var.set(folder)
            self.status("Ready. Click Scan.")

    def on_scan(self):
        folder = self.folder_var.get().strip()
        if not folder:
            return self.alert("Choose a folder first.")
        p = Path(folder)
        if not p.is_dir():
            return self.alert("Folder does not exist or is not a directory.")

        self.engine = HashEngine(self.algo_var.get(), int(self.hash_size_var.get()))
        self.stop_event.clear()
        self.scan_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.records.clear()
        self.groups.clear()
        self._clear_tree()
        self._clear_preview()
        self.status("Scanning…")

        def progress(i, total):
            self.pvar.set(0.0 if total == 0 else i / total)
            self.status(f"Scanning… {i}/{total} files processed")

        def worker():
            start = time.time()
            recs = ImageScanner(self.engine, self.stop_event).scan_folder(p, progress_cb=progress)
            if self.stop_event.is_set():
                self.status("Scan canceled.")
                self._after_scan_cleanup()
                return

            groups_raw = DupeGrouper(int(self.threshold_var.get())).build_groups(recs)
            gid = 1
            for _, members in groups_raw.items():
                for idx in members:
                    recs[idx].group_id = gid
                gid += 1

            self.records = recs
            self.groups = {}
            for i, r in enumerate(recs):
                if r.group_id is not None:
                    self.groups.setdefault(r.group_id, []).append(i)

            self.root.after(0, self._populate_tree)
            elapsed = time.time() - start
            dfiles = sum(len(v) for v in self.groups.values())
            gcount = len(self.groups)
            self.status(
                f"Found {gcount} duplicate groups ({dfiles} files) in {elapsed:.1f}s."
                if gcount else f"No duplicates found. Scanned {len(recs)} images in {elapsed:.1f}s."
            )
            self.root.after(0, self._after_scan_cleanup)

        threading.Thread(target=worker, daemon=True).start()

    def _after_scan_cleanup(self):
        self.scan_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.pvar.set(0.0)

    def on_cancel(self):
        self.stop_event.set()
        self.status("Canceling…")

    def on_toggle_mark_selected(self):
        changed = 0
        for iid in self.tree.selection():
            if self.tree.get_children(iid):  # parent (group)
                for child in self.tree.get_children(iid):
                    if child in self._iid_to_index:
                        idx = self._iid_to_index[child]
                        rec = self.records[idx]
                        rec.marked_for_delete = not rec.marked_for_delete
                        self._update_row_mark(child, rec)
                        changed += 1
            else:  # leaf
                if iid in self._iid_to_index:
                    idx = self._iid_to_index[iid]
                    rec = self.records[idx]
                    rec.marked_for_delete = not rec.marked_for_delete
                    self._update_row_mark(iid, rec)
                    changed += 1
        if changed:
            self.status(f"Toggled selection on {changed} file(s).")

    def on_select_non_best(self):
        count_marked = 0
        for _, idxs in self.groups.items():
            if not idxs:
                continue
            def score(i):
                r = self.records[i]
                return (r.width * r.height, r.size_bytes)
            best = max(idxs, key=score)
            for i in idxs:
                self.records[i].marked_for_delete = (i != best)
            count_marked += max(0, len(idxs) - 1)
        self._refresh_tree_marks()
        self.status(f"Selected {count_marked} files (kept best in each group).")

    def on_open_folder(self):
        sel = self.tree.selection()
        if not sel:
            return self.alert("Select at least one row.")
        iid = sel[0]
        if iid not in self._iid_to_index:
            children = self.tree.get_children(iid)
            if not children:
                return self.alert("No file rows under this item.")
            iid = children[0]
        idx = self._iid_to_index[iid]
        folder = self.records[idx].path.parent
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception as e:
            self.alert(f"Failed to open folder:\n{e}")

    def on_delete_marked(self):
        to_delete = [r for r in self.records if r.marked_for_delete]
        if not to_delete:
            return self.alert("No files are selected for deletion.")

        if send2trash:
            msg = f"Send {len(to_delete)} file(s) to Recycle Bin?"
        else:
            msg = f"PERMANENTLY delete {len(to_delete)} file(s)? (send2trash not installed)"

        if not self.confirm(msg, title="Confirm deletion"):
            return

        errors = 0
        remaining: List[ImageRecord] = []
        for r in self.records:
            if r.marked_for_delete:
                try:
                    if send2trash:
                        send2trash(str(r.path))
                    else:
                        r.path.unlink()
                except Exception:
                    errors += 1
                continue
            remaining.append(r)
        self.records = remaining

        new_groups: Dict[int, List[int]] = {}
        for i, r in enumerate(self.records):
            if r.group_id is not None:
                new_groups.setdefault(r.group_id, []).append(i)
        self.groups = {g: idxs for g, idxs in new_groups.items() if len(idxs) > 1}
        self._populate_tree()
        self.status("Deletion complete." if errors == 0 else f"Done, {errors} file(s) failed to delete.")

    def on_export_csv(self):
        if not self.groups:
            return self.alert("Nothing to export.")
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            title="Export CSV")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Group", "SelectedForDeletion", "Filename", "Resolution", "Size_MB", "Path"])
            for rec in self.records:
                if rec.group_id is None:
                    continue
                w.writerow([rec.group_id, int(rec.marked_for_delete), rec.path.name,
                            rec.resolution_str, f"{rec.size_mb:.2f}", str(rec.path)])
        self.status(f"Exported CSV to {path}")

    # ---------- Tree helpers ----------
    def _clear_tree(self):
        self._iid_to_index.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    def _populate_tree(self):
        self._clear_tree()
        for gid in sorted(self.groups.keys()):
            idxs = self.groups[gid]
            parent_iid = self.tree.insert(
                "", "end", text=f"Group {gid}  ({len(idxs)} files)"
            )
            for i in sorted(idxs, key=lambda k: self.records[k].path.name.lower()):
                rec = self.records[i]
                iid = self.tree.insert(
                    parent_iid, "end",
                    values=(
                        "✓" if rec.marked_for_delete else "—",
                        rec.path.name,
                        rec.resolution_str,
                        f"{rec.size_mb:.2f}",
                        str(rec.path),
                    )
                )
                self._iid_to_index[iid] = i
        self._clear_preview()

    def _update_row_mark(self, iid: str, rec: ImageRecord):
        self.tree.set(iid, "select", "✓" if rec.marked_for_delete else "—")

    def _refresh_tree_marks(self):
        for iid, idx in self._iid_to_index.items():
            self._update_row_mark(iid, self.records[idx])

    def _on_tree_select(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            self._clear_preview()
            return
        target = None
        for iid in sel:
            if iid in self._iid_to_index:
                target = iid
                break
        if target is None:
            self._clear_preview()
            return
        idx = self._iid_to_index[target]
        self._show_preview(self.records[idx].path)

    def _on_tree_double_click(self, evt):
        region = self.tree.identify("region", evt.x, evt.y)
        if region != "cell":
            return
        col = self.tree.identify_column(evt.x)
        row = self.tree.identify_row(evt.y)
        if not row or row not in self._iid_to_index:
            return 
        if col != "#1": 
            return
        idx = self._iid_to_index[row]
        rec = self.records[idx]
        rec.marked_for_delete = not rec.marked_for_delete
        self._update_row_mark(row, rec)

    # ---------- Preview ----------
    def _clear_preview(self):
        self._preview_pil = None
        self._preview_photo = None
        self._preview_path = None
        self.preview_canvas.delete("all")

    def _show_preview(self, path: Path):
        try:
            with Image.open(path) as im:
                try:
                    im.seek(0)
                except Exception:
                    pass
                im = ImageOps.exif_transpose(im)
                if im.mode not in ("RGB", "RGBA", "L"):
                    im = im.convert("RGB")
                self._preview_pil = im.copy()
                self._preview_path = path
        except Exception:
            self._preview_pil = None
            self._preview_path = None
        self._render_preview()

    def _on_preview_resize(self, _evt):
        self._render_preview()

    def _render_preview(self):
        self.preview_canvas.delete("all")
        if self._preview_pil is None:
            self.preview_canvas.create_text(
                self.preview_canvas.winfo_width() // 2,
                self.preview_canvas.winfo_height() // 2,
                text="(Preview unavailable)",
                fill="#aaa"
            )
            return
        cw = max(1, self.preview_canvas.winfo_width())
        ch = max(1, self.preview_canvas.winfo_height())
        img = self._preview_pil.copy()
        img.thumbnail((cw, ch), Image.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(img)
        self.preview_canvas.create_image(cw // 2, ch // 2, image=self._preview_photo, anchor="center")
        self.preview_canvas.create_rectangle(2, 2, cw - 2, ch - 2, outline="#333")

    # ---------- UX ----------
    def status(self, text: str):
        self.status_var.set(text)
        if hasattr(self.root, "update_idletasks"):
            self.root.update_idletasks()

    def alert(self, message: str, title: str = "Notice"):
        if self.StyleMsg:
            self.StyleMsg.show_info(message=message, title=title)
        else:
            tk_messagebox.showinfo(title, message)

    def confirm(self, message: str, title: str = "Confirm") -> bool:
        if self.StyleMsg:
            return self.StyleMsg.okcancel(message=message, title=title) == "OK"
        else:
            return tk_messagebox.askokcancel(title, message)

    def run(self):
        self.root.mainloop()

# ---------- Main ----------
if __name__ == "__main__":
    app = DuplicateFinderApp()
    app.run()
