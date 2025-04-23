import os
from PIL import Image
import imagehash
import PySimpleGUI as sg
from io import BytesIO

# --- Settings ---
HASH_TOLERANCE = 5  # Hash difference tolerance; lower = stricter match
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# --- Helper Functions ---
def load_image_thumbnail(path, max_size=(150, 150)):
    try:
        img = Image.open(path)
        img.thumbnail(max_size)
        bio = BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()
    except:
        return None

def get_image_files(folder):
    return [os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().endswith(SUPPORTED_FORMATS)]

def find_duplicates(paths):
    hashes = {}
    duplicates = []

    for path in paths:
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

    for group in hashes.values():
        if len(group) > 1:
            duplicates.append(group)
    return duplicates

# --- GUI ---
sg.theme("DarkBlue3")

folder = sg.popup_get_folder("Select folder with images", title="Find Image Duplicates")
if not folder:
    exit()

image_paths = get_image_files(folder)
duplicates = find_duplicates(image_paths)

if not duplicates:
    sg.popup("No duplicates found 🎉")
    exit()

# Layout for displaying duplicate groups
group_layouts = []
for group in duplicates:
    images = []
    for path in group:
        thumb = load_image_thumbnail(path)
        if thumb:
            images.append(sg.Image(data=thumb, pad=(5, 5)))
            images.append(sg.Text(os.path.basename(path), size=(30, 1), pad=(5, 10)))
    group_layouts.append([sg.Frame("Duplicate Group", [images], pad=(10, 10))])

layout = [[sg.Column(group_layouts, scrollable=True, vertical_scroll_only=True, size=(800, 600))],
          [sg.Button("Close")]]

window = sg.Window("Image Duplicate Finder", layout, finalize=True)

while True:
    event, values = window.read()
    if event == sg.WIN_CLOSED or event == "Close":
        break

window.close()
