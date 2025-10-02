# Duplicate Finder
A single-file Tkinter Python app to detect and manage duplicate or near-duplicate images. 
Uses **Pillow** + **imagehash** for perceptual hashing, shows results with live **preview**, CSV export, and deletion to the system recycle bin.

## Requirements
Install dependencies with:

```bash
# needed
pip install Pillow imagehash
pip install send2trash ttkbootstrap
# optional
pip install pillow-heif
```

## Run
```bash
python finder.py
```

## Usage
1. Select Folder (all subfolders are scanned)
2. (Optional) Choose Algorithm (phash default), Hash size (default 16), and Threshold (default 5)
3. Click Scan
4. Review duplicate groups. Click a file to preview (EXIF-aware, resizes; GIF shows first frame)
5. (Optional) Use Select all NON-best per group (keeps highest resolution / largest)
6. Delete selected (recycle bin with send2trash), Export CSV, or Open containing folder.

#### Settings (tips)
Algorithms:
- phash is a solid default
- dhash/ahash are faster
- whash/colorhash can be more sensitive

Threshold:
- lower (0–2) = stricter
- ~5 for near-dupes
- higher (6–10) catches more but may group false positives

## Changelog

| Version | Changes                                                                                     |
|---------|---------------------------------------------------------------------------------------------|
| v3.0  | Reworked UI completely, added different algorithms, multithreaded scan and other options. |
| v2.1  | Added threaded scanning to keep the UI responsive and fixed crashes on large folders. |
| v2.0  | Switched to tkinter and implemented dark design |
| v1.7  | Added pagination                                        |
| v1.6  | Added a toggle to include subfolders in the search.                                         |
| v1.5  | Automatically starts a new subprocess after finding no duplicates or after deletion.        |
| v1.4  | Improved error handling when deleting files (e.g., file in use by another process).         |
| v1.3  | Increased image thumbnail size for better visibility.                                       |
| v1.2  | Displayed image resolutions alongside thumbnails.                                           |
| v1.1  | Added a "Delete Selected" button to allow users to delete marked duplicate files.           |
| v1.0  | Initial release with duplicate detection and grouping using perceptual hashing (pHash).    |
