# Duplicate Finder
A Python script to detect and manage duplicate image files in a folder. It uses `PySimpleGUI` for the GUI and `Pillow` with `imagehash` for image comparison.

## Requirements
Install dependencies with:

```bash
pip install Pillow imagehash PySimpleGUI
```

## Settings
- **HASH_TOLERANCE**: Adjust similarity sensitivity (default: `5`).
- **SUPPORTED_FORMATS**: Modify supported image formats.

## Changelog

| Version | Changes                                                                                     |
|---------|---------------------------------------------------------------------------------------------|
| v1.6  | Added a toggle to include subfolders in the search.                                         |
| v1.5  | Automatically starts a new subprocess after finding no duplicates or after deletion.        |
| v1.4  | Improved error handling when deleting files (e.g., file in use by another process).         |
| v1.3  | Increased image thumbnail size for better visibility.                                       |
| v1.2  | Displayed image resolutions alongside thumbnails.                                           |
| v1.1  | Added a "Delete Selected" button to allow users to delete marked duplicate files.           |
| v1.0  | Initial release with duplicate detection and grouping using perceptual hashing (pHash).    |
