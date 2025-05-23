import os
import sys
from PIL import Image
import imagehash
import PySimpleGUI as sg
from io import BytesIO
import shlex 
import subprocess  

# --- Settings ---
HASH_TOLERANCE = 5  # Hash difference tolerance; lower = stricter match
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# --- Helper Functions ---
def load_image_thumbnail(path, max_size=(250, 250)):
    try:
        img = Image.open(path)
        img.thumbnail(max_size)
        bio = BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()
    except:
        return None

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

def update_progress(current, total):
    progress_bar.UpdateBar(current, total)
    progress_text.update(f"Processing image {current}/{total}")

def find_duplicates(paths, progress_callback=None):
    hashes = {}
    duplicates = []

    for i, path in enumerate(paths):
        try:
            img = Image.open(path)
            hash = imagehash.phash(img)

            found = False
            for h, group in hashes.items():
                if hash - h < HASH_TOLERANCE:
                    group.append(path)
                    found = True
                    break
            if not found:
                hashes[hash] = [path]
        except:
            continue

        if progress_callback:
            progress_callback(i + 1, len(paths))

    for group in hashes.values():
        if len(group) > 1:
            duplicates.append(group)
    return duplicates

# --- GUI ---
sg.theme("DarkBlue3")

layout_start = [
    [sg.Text("Select folder with images:")],
    [sg.Input(key="FOLDER"), sg.FolderBrowse()],
    [sg.Checkbox("Include Subfolders", key="INCLUDE_SUBFOLDERS", default=False)],
    [sg.Button("Start"), sg.Button("Cancel")]
]

start_window = sg.Window("Find Image Duplicates - Settings", layout_start)

event, values = start_window.read()
if event in (sg.WIN_CLOSED, "Cancel"):
    start_window.close()
    exit()

folder = values["FOLDER"]
include_subfolders = values["INCLUDE_SUBFOLDERS"]
start_window.close()

if not folder:
    sg.popup("No folder selected. Exiting.")
    exit()

image_paths = get_image_files(folder, include_subfolders)

progress_layout = [
    [sg.Text("Checking images for duplicates...", key="PROGRESS_TEXT")],
    [sg.ProgressBar(len(image_paths), orientation='h', size=(50, 20), key="PROGRESS")],
]
progress_window = sg.Window("Progress", progress_layout, finalize=True)
progress_bar = progress_window["PROGRESS"]
progress_text = progress_window["PROGRESS_TEXT"]

duplicates = find_duplicates(image_paths, progress_callback=update_progress)
progress_window.close()  

if not duplicates:
    sg.popup("No duplicates found 🎉")
    progress_window.close()
    subprocess.Popen([sys.executable] + sys.argv)
    sys.exit()

def create_page_layout(groups, page, groups_per_page=50):
    start = page * groups_per_page
    end = start + groups_per_page
    group_layouts = []

    for group in groups[start:end]:
        group_elements = []
        for path in group:
            thumb = load_image_thumbnail(path)
            if thumb:
                try:
                    with Image.open(path) as img:
                        resolution = f"{img.width}x{img.height}"
                except:
                    resolution = "Unknown"

                row = [
                    sg.Checkbox("", key=f"MARK::{path}", pad=(5, 5)),
                    sg.Image(data=thumb, pad=(5, 5)),
                    sg.Column([
                        [sg.Text(os.path.basename(path), size=(40, 1), pad=(5, 5))],  
                        [sg.Text(f"Resolution: {resolution}", size=(20, 1), pad=(5, 5))],  
                        [sg.Text(f"Path: {path}", size=(60, 1), pad=(5, 5))]  
                    ], vertical_alignment="center", pad=(5, 5))
                ]
                group_elements.append(row)

        group_layouts.append([sg.Frame(f"Duplicate Group ({len(group)} items)", group_elements, pad=(10, 10))])

    layout = [
        [sg.Column(group_layouts, scrollable=True, vertical_scroll_only=True, size=(800, 600))],
        [
            sg.Button("Previous", size=(10, 1)),
            sg.Text(f"Page {page + 1}/{total_pages}", key="PAGE_TEXT", size=(15, 1), justification="center"),
            sg.Button("Next", size=(10, 1)),
            sg.Button("Delete Selected", size=(15, 1)),
            sg.Button("Restart", size=(10, 1)),
            sg.Button("Close", size=(10, 1))
        ]
    ]
    return layout

current_page = 0
groups_per_page = 50
total_pages = (len(duplicates) + groups_per_page - 1) // groups_per_page

layout = create_page_layout(duplicates, current_page)
window = sg.Window("Image Duplicate Finder", layout, finalize=True)

while True:
    event, values = window.read()
    if event == sg.WIN_CLOSED or event == "Close":
        break
    if event == "Restart":
        window.close()
        subprocess.Popen([sys.executable] + sys.argv)  
        sys.exit()
    if event == "Delete Selected":
        files_to_delete = [key.split("::")[1] for key, value in values.items() if key.startswith("MARK::") and value]
        if files_to_delete:
            confirm = sg.popup_yes_no(f"Are you sure you want to delete {len(files_to_delete)} files?")
            if confirm == "Yes":
                for file_to_delete in files_to_delete:
                    try:
                        os.remove(file_to_delete)
                    except Exception as e:
                        sg.popup(f"Error deleting file: {file_to_delete}\n{e}")
                sg.popup(f"Deleted {len(files_to_delete)} files.")
                
                duplicates = [[path for path in group if path not in files_to_delete] for group in duplicates]
                duplicates = [group for group in duplicates if group] 
                
                total_pages = (len(duplicates) + groups_per_page - 1) // groups_per_page
                
                if not duplicates:
                    sg.popup("All duplicates have been processed. Restarting...")
                    window.close()
                    subprocess.Popen([sys.executable] + sys.argv)
                    sys.exit()
                
                if current_page >= total_pages:
                    current_page = max(0, total_pages - 1)
                
                window.close()
                layout = create_page_layout(duplicates, current_page)
                window = sg.Window("Image Duplicate Finder", layout, finalize=True)
    if event == "Next" and current_page < total_pages - 1:
        current_page += 1
        window["PAGE_TEXT"].update(f"Page {current_page + 1}/{total_pages}")
        window.close()
        layout = create_page_layout(duplicates, current_page)
        window = sg.Window("Image Duplicate Finder", layout, finalize=True)
    if event == "Previous" and current_page > 0:
        current_page -= 1
        window["PAGE_TEXT"].update(f"Page {current_page + 1}/{total_pages}")
        window.close()
        layout = create_page_layout(duplicates, current_page)
        window = sg.Window("Image Duplicate Finder", layout, finalize=True)

window.close()
