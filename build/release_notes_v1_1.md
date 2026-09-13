# ComfyUI PNG to WebP Migration Tool - v1.1

The first official release of the **ComfyUI PNG to WebP Migration Tool**! This command-line utility migrates ComfyUI-generated PNG images to optimized, web-friendly WebP files while fully preserving your valuable workflows and generation prompts.

## Key Features

- **High-Performance WebP Compression**: Dramatically reduces storage requirements (lossy WebP compression, defaulting to 85% quality) with customization options from 1 to 100.
- **Workflow & Prompt Metadata Preservation**: Translates PNG text chunks (visual graph workflows and API prompts) into standard WebP EXIF tags (`Make` and `ImageDescription`), enabling ComfyUI to read workflows directly from the resulting WebP files via drag-and-drop.
- **Base64 Payload Filtering**: Automatically strips large base64-encoded strings (like embedded input images or masks) from workflow metadata to prevent EXIF chunk length overflows.
- **Built-in Help Page**: Running `png2webp -h` (or `--help`) prints a complete overview directly in the terminal: a description of the tool, every parameter with its default value, usage examples, and the tool's safety defaults.
- **Dry-run Mode**: Simulates the migration process, providing total image counts and estimating space savings without making any disk modifications.
- **Safeguards & Overwrite Options**: Built-in protection prevents overwriting existing files or deleting original PNG files unless explicitly requested.
- **Subdirectory Traversal**: Option to process folders recursively.
- **Multiprocessing Support**: Spreads tasks across multiple CPU cores for fast batch processing.
- **Creation/Modification Timestamp Preservation**: Retains the original file modification and access times using the `-p` or `--preserve` option.

---

## Standalone Platform Binaries

Standalone executables that run **without requiring a Python installation** are packaged inside platform-specific archives:

- **Windows**: `png2webp-windows.zip` (contains `png2webp.exe`)
- **Linux**: `png2webp-linux.tar.gz` (contains `png2webp`)
- **macOS**: `png2webp-macos.tar.gz` (contains `png2webp`)

---

## Quick Start

Download the archive matching your platform, extract the executable, and run it from your command line.

### 1. Show the Built-in Help

```bash
# Display the full help page: parameters, defaults, and usage examples
./png2webp -h
```

### 2. Preview Space Savings (Dry Run)

```bash
# Preview how many files will be converted and how much space will be saved
./png2webp --dry-run
```

### 3. Standard Conversion

```bash
# Convert all PNGs in the current directory with verbose logging
./png2webp -v
```

### 4. Advanced Migration (Recursive, Separate Destination, Preserve Timestamps)

```bash
# Recursively convert folder contents, output to a destination folder, and preserve timestamps
./png2webp /path/to/source -f /path/to/destination -r -p -v
```

---

## CLI Arguments

| Argument | Shorthand | Description |
| :--- | :--- | :--- |
| `--help` | `-h` | Display the built-in help page with an overview of all parameters, their defaults, and usage examples. |
| `path` | | Directory containing PNG files to convert. Defaults to the current directory (`.`). |
| `--destination` | `-f` | Destination directory to save the output WebP images (retains nested subdirectory structure if `--recursive` is enabled). |
| `--quality` | `-q` | Compression quality for the WebP output from `1` to `100`. (Default: `85`). |
| `--recursive` | `-r` | Recursively scan subdirectories for PNG files. |
| `--overwrite` | `-o` | Overwrite existing WebP files with the same name. (Default: skip them). |
| `--delete-source` | `-d` | **Caution**: Delete the original `.png` files after successful conversion. (Default: keep them). |
| `--dry-run` | | Perform a trial run showing which files would be converted and how much space would be saved without writing or deleting files. |
| `--verbose` | `-v` | Enable detailed output for each file processed. |
| `--workers` | `-w` | Number of parallel worker processes to use (default: `min(4, CPU count)`). |
| `--preserve` | `-p` | Preserve original file modification and access times on the output WebP images. |

---

## Installation via Source

If you prefer to run the tool via Python, ensure you have Python 3 installed. The script depends on the following libraries:

- `Pillow` (PIL) - For image loading and saving
- `piexif` - For writing EXIF headers inside WebP (falls back to native Pillow EXIF writing if not installed)
- `pyinstaller` - For building standalone binaries (optional, development only)

1. Clone the repository.
2. Initialize and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Run the script:

   ```bash
   python png2webp.py [arguments]
   ```

---

## Testing

A test suite `test_png2webp.py` is included to verify the image migration and metadata cleaning logic using your own test images:

1. Place your ComfyUI-generated PNG files (containing visual workflows and prompts) inside the `test_images` folder in the workspace root.
2. Run the test script:

   ```bash
   python test_png2webp.py
   ```

3. The script processes each PNG in `test_images`, converts it to WebP (without deleting the original PNG), and verifies that:
   - The output WebP file is successfully created.
   - The `Make` EXIF tag is correctly populated with the `prompt:` JSON.
   - The `ImageDescription` EXIF tag is correctly populated with the `workflow:` JSON.
   - Large base64-encoded strings (like embedded images/masks) are successfully cleaned out of the workflow.
   - All EXIF payloads are structured and prefixed in accordance with ComfyUI specifications.
   - Timestamps are preserved correctly when using the `-p` option.

---

## Building from Source

You can compile the Python script into a standalone executable using PyInstaller:

```bash
# Build using the checked-in spec file
pyinstaller --clean -y png2webp.spec
```

The standalone executable is placed in `dist/` (`png2webp.exe` on Windows, `png2webp` on Linux/macOS). Automated builds for all three platforms run on every push and tag via GitHub Actions, and releases are published automatically when a `v*` tag is pushed.

---

## Acknowledgments

This utility is adapted from the [ComfyUI-SaveCompressed-Weppy](https://github.com/skkut/ComfyUI-SaveCompressed-Weppy) repository.
