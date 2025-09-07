import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import imagehash
import datetime

HASH_TOLERANCE = 5
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

DARK_BG = "#23272e"
DARK_FG = "#f5f6fa"
ACCENT = "#3b82f6"
BTN_BG = "#2d333b"
BTN_ACTIVE = "#3b4252"
CHECK_BG = "#23272e"
CHECK_ACTIVE = "#000000"

def get_image_files(folder, include_subfolders=False):
    image_files = []
    if include_subfolders:
        for root, _, files in os.walk(folder):
            image_files.extend(
                os.path.join(root, f) for f in files if f.lower().endswith(SUPPORTED_FORMATS)
            )
    else:
        image_files = [
            os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(SUPPORTED_FORMATS)
        ]
    return image_files

def find_duplicates(paths, progress_callback=None):
    hashes = {}
    duplicates = []
    for i, path in enumerate(paths):
        try:
            with Image.open(path) as img:
                hash = imagehash.phash(img)
            found = False
            for h, group in hashes.items():
                if hash - h < HASH_TOLERANCE:
                    group.append(path)
                    found = True
                    break
            if not found:
                hashes[hash] = [path]
        except Exception:
            continue
        if progress_callback:
            progress_callback(i + 1, len(paths))
    for group in hashes.values():
        if len(group) > 1:
            duplicates.append(group)
    return duplicates

class DuplicateFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Duplicate Finder (Tkinter)")
        self.root.configure(bg=DARK_BG)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=DARK_BG)
        style.configure("TLabel", background=DARK_BG, foreground=DARK_FG)
        style.configure("TButton", background=BTN_BG, foreground=DARK_FG, borderwidth=0, focusthickness=3, focuscolor=ACCENT)
        style.map("TButton", background=[("active", BTN_ACTIVE)])
        style.configure("Vertical.TScrollbar", background=BTN_BG, troughcolor=DARK_BG, bordercolor=BTN_BG, arrowcolor=ACCENT)
        self.folder = ""
        self.include_subfolders = tk.BooleanVar()
        self.duplicates = []
        self.current_page = 0
        self.groups_per_page = 50
        self.groups_per_row = 2
        self.selected = set()
        self.image_cache = {}
        self.build_start_screen()

    def build_start_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.root, bg=DARK_BG)
        frame.pack(padx=20, pady=20)
        tk.Label(frame, text="Select folder with images:", bg=DARK_BG, fg=DARK_FG, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.folder_entry = tk.Entry(frame, width=50, bg=BTN_BG, fg=DARK_FG, insertbackground=ACCENT, relief="flat", font=("Segoe UI", 11))
        self.folder_entry.grid(row=1, column=0, padx=5, pady=5)
        tk.Button(frame, text="Browse", command=self.browse_folder, bg=BTN_BG, fg=DARK_FG, activebackground=BTN_ACTIVE, activeforeground=ACCENT, relief="flat", font=("Segoe UI", 11)).grid(row=1, column=1, padx=5)
        tk.Checkbutton(frame, text="Include Subfolders", variable=self.include_subfolders, bg=DARK_BG, fg=DARK_FG, selectcolor=CHECK_ACTIVE, activebackground=DARK_BG, font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w")
        tk.Button(frame, text="Start", command=self.start_search, bg=ACCENT, fg=DARK_BG, activebackground=BTN_ACTIVE, activeforeground=DARK_FG, relief="flat", font=("Segoe UI", 11, "bold")).grid(row=3, column=0, pady=10)
        tk.Button(frame, text="Exit", command=self.root.quit, bg=BTN_BG, fg=DARK_FG, activebackground=BTN_ACTIVE, activeforeground=ACCENT, relief="flat", font=("Segoe UI", 11)).grid(row=3, column=1, pady=10)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)

    def start_search(self):
        self.folder = self.folder_entry.get()
        if not self.folder or not os.path.isdir(self.folder):
            messagebox.showerror("Error", "No valid folder selected.")
            return
        self.image_paths = get_image_files(self.folder, self.include_subfolders.get())
        if not self.image_paths:
            messagebox.showinfo("Info", "No images found in the selected folder.")
            return
        self.show_progress_and_find_duplicates()

    def show_progress_and_find_duplicates(self):
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Progress")
        progress_win.configure(bg=DARK_BG)
        tk.Label(progress_win, text="Checking images for duplicates...", bg=DARK_BG, fg=ACCENT, font=("Segoe UI", 12, "bold")).pack(padx=10, pady=10)
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_win, maximum=len(self.image_paths), variable=progress_var, length=400)
        progress_bar.pack(padx=10, pady=10)
        progress_text = tk.Label(progress_win, text=f"Processing image 0/{len(self.image_paths)}", bg=DARK_BG, fg=DARK_FG, font=("Segoe UI", 11))
        progress_text.pack(padx=10, pady=5)

        def update_progress(current, total):
            def _update():
                progress_var.set(current)
                progress_text.config(text=f"Processing image {current}/{total}")
            self.root.after(0, _update)

        def worker():
            duplicates = find_duplicates(self.image_paths, progress_callback=update_progress)

            def on_done():
                progress_win.destroy()
                self.duplicates = duplicates
                if not self.duplicates:
                    messagebox.showinfo("Result", "No duplicates found 🎉")
                    self.build_start_screen()
                    return
                self.current_page = 0
                self.selected = set()
                self.build_results_screen()

            self.root.after(0, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def build_results_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        nav_frame = tk.Frame(self.root, bg=DARK_BG)
        nav_frame.pack(fill="x", pady=5)
        tk.Button(nav_frame, text="Previous", command=self.prev_page, bg=BTN_BG, fg=DARK_FG, activebackground=BTN_ACTIVE, activeforeground=ACCENT, relief="flat", font=("Segoe UI", 11)).pack(side="left", padx=5)
        tk.Label(nav_frame, text=f"Page {self.current_page+1}/{self.total_pages()}", bg=DARK_BG, fg=ACCENT, font=("Segoe UI", 11, "bold")).pack(side="left", padx=5)
        tk.Button(nav_frame, text="Next", command=self.next_page, bg=BTN_BG, fg=DARK_FG, activebackground=BTN_ACTIVE, activeforeground=ACCENT, relief="flat", font=("Segoe UI", 11)).pack(side="left", padx=5)
        tk.Button(nav_frame, text="Delete Selected", command=self.delete_selected, bg=ACCENT, fg=DARK_BG, activebackground=BTN_ACTIVE, activeforeground=DARK_FG, relief="flat", font=("Segoe UI", 11, "bold")).pack(side="right", padx=5)
        tk.Button(nav_frame, text="Restart", command=self.restart, bg=BTN_BG, fg=DARK_FG, activebackground=BTN_ACTIVE, activeforeground=ACCENT, relief="flat", font=("Segoe UI", 11)).pack(side="right", padx=5)
        tk.Button(nav_frame, text="Exit", command=self.root.quit, bg=BTN_BG, fg=DARK_FG, activebackground=BTN_ACTIVE, activeforeground=ACCENT, relief="flat", font=("Segoe UI", 11)).pack(side="right", padx=5)

        canvas = tk.Canvas(self.root, width=1400, height=800, bg=DARK_BG, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        scroll_y = tk.Scrollbar(self.root, orient="vertical", command=canvas.yview, troughcolor=BTN_BG, bg=BTN_BG, activebackground=ACCENT)
        scroll_y.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scroll_y.set)
        frame = tk.Frame(canvas, bg=DARK_BG)
        canvas.create_window((0, 0), window=frame, anchor="nw")

        groups = self.duplicates[self.current_page*self.groups_per_page:(self.current_page+1)*self.groups_per_page]
        for idx, group in enumerate(groups):
            row = idx // self.groups_per_row
            col = idx % self.groups_per_row
            group_frame = tk.LabelFrame(frame, text=f"Duplicate Group ({len(group)} items)", padx=10, pady=10, bg=BTN_BG, fg=ACCENT, font=("Segoe UI", 11, "bold"), relief="groove", bd=2, labelanchor="n")
            group_frame.grid(row=row, column=col, padx=16, pady=16, sticky="nw")
            for i, path in enumerate(group):
                thumb = self.get_thumbnail(path, max_size=(200, 200))
                var = tk.BooleanVar(value=path in self.selected)
                cb = tk.Checkbutton(group_frame, variable=var, command=lambda p=path, v=var: self.toggle_select(p, v),
                                   bg=BTN_BG, fg=ACCENT, selectcolor=CHECK_ACTIVE, activebackground=BTN_ACTIVE, font=("Segoe UI", 10))
                cb.grid(row=i, column=0, sticky="n", padx=2)
                if thumb:
                    lbl = tk.Label(group_frame, image=thumb, bg=BTN_BG)
                    lbl.image = thumb
                    lbl.grid(row=i, column=1, sticky="n", padx=2)
                try:
                    with Image.open(path) as img:
                        resolution = f"{img.width}x{img.height}"
                except:
                    resolution = "Unknown"
                rel_path = os.path.relpath(path, self.folder)
                try:
                    ctime = os.path.getctime(path)
                    date_str = datetime.datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M')
                except:
                    date_str = "Unknown"
                tk.Label(group_frame, text=os.path.basename(path), width=40, anchor="w", bg=BTN_BG, fg=DARK_FG, font=("Segoe UI", 10, "bold")).grid(row=i, column=2, sticky="w")
                tk.Label(group_frame, text=f"Resolution: {resolution}", width=18, anchor="w", bg=BTN_BG, fg=ACCENT, font=("Segoe UI", 10)).grid(row=i, column=3, sticky="w")
                tk.Label(group_frame, text=rel_path, width=50, anchor="w", bg=BTN_BG, fg="b0b0b0", font=("Segoe UI", 9, "italic")).grid(row=i, column=4, sticky="w")
                tk.Label(group_frame, text=f"Created: {date_str}", width=20, anchor="w", bg=BTN_BG, fg="#b0b0b0", font=("Segoe UI", 9)).grid(row=i, column=5, sticky="w")
        frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

    def get_thumbnail(self, path, max_size=(200, 200)):
        if path in self.image_cache:
            return self.image_cache[path]
        try:
            with Image.open(path) as img:
                img.thumbnail(max_size)
                thumb = ImageTk.PhotoImage(img.copy())
            self.image_cache[path] = thumb
            return thumb
        except Exception:
            return None

    def toggle_select(self, path, var):
        if var.get():
            self.selected.add(path)
        else:
            self.selected.discard(path)

    def delete_selected(self):
        if not self.selected:
            messagebox.showinfo("Info", "No images selected.")
            return
        if not messagebox.askyesno("Confirm", f"Delete {len(self.selected)} selected files?"):
            return
        for file_path in list(self.selected):
            try:
                os.remove(file_path)
            except Exception as e:
                messagebox.showerror("Error", f"Error deleting file: {file_path}\n{e}")
        self.duplicates = [[p for p in group if p not in self.selected] for group in self.duplicates]
        self.duplicates = [group for group in self.duplicates if group]
        self.selected.clear()
        if not self.duplicates:
            messagebox.showinfo("Info", "All duplicates have been processed. Restarting...")
            self.restart()
            return
        if self.current_page >= self.total_pages():
            self.current_page = max(0, self.total_pages() - 1)
        self.build_results_screen()

    def total_pages(self):
        return (len(self.duplicates) + self.groups_per_page - 1) // self.groups_per_page

    def next_page(self):
        if self.current_page < self.total_pages() - 1:
            self.current_page += 1
            self.build_results_screen()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.build_results_screen()

    def restart(self):
        python = sys.executable
        os.execl(python, python, *sys.argv)

if __name__ == "__main__":
    root = tk.Tk()
    app = DuplicateFinderApp(root)
    root.mainloop()
