#!/usr/bin/env python3
import os
import json
import argparse
import sys
import multiprocessing
from pathlib import Path
from PIL import Image

try:
    import piexif
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False

# Tag values (EXIF standard)
# Make = 271 (0x010f), ImageDescription = 270 (0x010e)
TAG_MAKE = 0x010f
TAG_IMAGE_DESCRIPTION = 0x010e

def strip_binary_from_workflow(value):
    """
    Strips large base64-encoded/binary items from the ComfyUI workflow JSON
    to prevent EXIF data size limit errors when saving to WebP.
    """
    if isinstance(value, dict):
        return {k: strip_binary_from_workflow(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [strip_binary_from_workflow(v) for v in value]
    elif isinstance(value, str):
        if value.startswith("data:") and ";base64," in value:
            return ""
        if len(value) > 10240 and " " not in value:
            return ""
    return value

def clean_metadata(raw_val):
    """
    Decode if bytes, parse JSON, clean binary data, and return a JSON string.
    """
    if raw_val is None:
        return None
    
    if isinstance(raw_val, bytes):
        try:
            raw_val = raw_val.decode('utf-8', errors='ignore')
        except Exception:
            pass
            
    if not isinstance(raw_val, str):
        try:
            cleaned = strip_binary_from_workflow(raw_val)
            return json.dumps(cleaned)
        except Exception:
            return str(raw_val)
            
    try:
        parsed = json.loads(raw_val)
        cleaned = strip_binary_from_workflow(parsed)
        return json.dumps(cleaned)
    except Exception:
        # Fallback for plain strings
        return strip_binary_from_workflow(raw_val)

def generate_webp_exif(img, prompt, workflow):
    """
    Generate EXIF bytes using piexif (if available) or Pillow's native Exif container.
    """
    prompt_str = f"prompt:{prompt}" if prompt else None
    workflow_str = f"workflow:{workflow}" if workflow else None
    
    if PIEXIF_AVAILABLE:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        if prompt_str:
            exif_dict["0th"][piexif.ImageIFD.Make] = prompt_str.encode("utf-8")
        if workflow_str:
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = workflow_str.encode("utf-8")
        try:
            return piexif.dump(exif_dict)
        except Exception as e:
            print(f"Error compiling EXIF via piexif: {e}. Falling back to Pillow native EXIF.")
            # Fall back to Pillow native Exif
    
    # Pillow native EXIF fallback
    try:
        exif = img.getexif()
        if prompt_str:
            exif[TAG_MAKE] = prompt_str.encode("utf-8")
        if workflow_str:
            exif[TAG_IMAGE_DESCRIPTION] = workflow_str.encode("utf-8")
        return exif
    except Exception as e:
        print(f"Error creating native EXIF: {e}")
        return None

def set_creation_time_windows(file_path, timestamp):
    """
    Sets the creation time of a file on Windows.
    `timestamp` is a Unix epoch timestamp (seconds since Jan 1, 1970).
    """
    import ctypes
    from ctypes import wintypes
    
    # Windows FILETIME is 100-nanosecond intervals since January 1, 1601 (UTC).
    # 11644473600 is the difference in seconds between 1601 and 1970.
    filetime_val = int((timestamp + 11644473600) * 10000000)
    
    # Split the 64-bit value into low and high 32-bit parts
    low = filetime_val & 0xFFFFFFFF
    high = (filetime_val >> 32) & 0xFFFFFFFF
    ft_creation = wintypes.FILETIME(low, high)
    
    # Open handle to the file with GENERIC_WRITE access
    handle = ctypes.windll.kernel32.CreateFileW(
        str(file_path),
        0x40000000, # GENERIC_WRITE
        0x00000007, # FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
        None,
        3,          # OPEN_EXISTING
        0x02000000, # FILE_FLAG_BACKUP_SEMANTICS
        None
    )
    
    if handle == -1 or handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError()
        
    try:
        # SetFileTime(hFile, lpCreationTime, lpLastAccessTime, lpLastWriteTime)
        # Passing None for access and write times leaves them unchanged
        success = ctypes.windll.kernel32.SetFileTime(
            handle,
            ctypes.byref(ft_creation),
            None,
            None
        )
        if not success:
            raise ctypes.WinError()
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)

def convert_png_to_webp(png_path, quality=85, overwrite=False, delete_source=False, dry_run=False, verbose=False, webp_path=None, preserve_timestamp=False):
    """
    Converts a single PNG file to WebP format, extracting and embedding ComfyUI workflow/prompt metadata.
    """
    png_path = Path(png_path)
    if webp_path is None:
        webp_path = png_path.with_suffix('.webp')
    else:
        webp_path = Path(webp_path)
    
    if webp_path.exists() and not overwrite:
        if verbose:
            print(f"[SKIP] WebP file already exists: {webp_path}")
        return "skipped_exists", 0, 0
    
    try:
        # Get source file details
        src_stat = png_path.stat()
        src_size = src_stat.st_size
        
        # Load PNG and extract metadata
        with Image.open(png_path) as img:
            prompt_raw = img.info.get('prompt')
            workflow_raw = img.info.get('workflow')
            
            prompt_cleaned = clean_metadata(prompt_raw)
            workflow_cleaned = clean_metadata(workflow_raw)
            
            has_metadata = (prompt_cleaned is not None) or (workflow_cleaned is not None)
            
            if dry_run:
                import io
                temp_buffer = io.BytesIO()
                exif_data = generate_webp_exif(img, prompt_cleaned, workflow_cleaned)
                save_args = {
                    'format': 'WEBP',
                    'quality': quality,
                    'lossless': False
                }
                if exif_data is not None:
                    save_args['exif'] = exif_data
                img.save(temp_buffer, **save_args)
                dest_size = temp_buffer.tell()
                
                if verbose:
                    meta_info = "with metadata" if has_metadata else "no metadata found"
                    preserve_info = ", preserve times" if preserve_timestamp else ""
                    size_diff = src_size - dest_size
                    pct = (size_diff / src_size * 100) if src_size > 0 else 0
                    print(f"[DRY-RUN] Would convert {png_path.name} -> {webp_path} ({meta_info}{preserve_info}, Est WebP: {dest_size/1024:.1f}KB, Saved: {size_diff/1024:.1f}KB / {pct:.1f}%)")
                return "dry_run", src_size, dest_size
                
            # Build Exif
            exif_data = generate_webp_exif(img, prompt_cleaned, workflow_cleaned)
            
            # Save as WebP
            save_args = {
                'format': 'WEBP',
                'quality': quality,
                'lossless': False
            }
            if exif_data is not None:
                save_args['exif'] = exif_data
                
            if not dry_run:
                webp_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(webp_path, **save_args)
            
        # Get destination file size
        dest_size = webp_path.stat().st_size
        
        if preserve_timestamp and not dry_run:
            try:
                os.utime(webp_path, (src_stat.st_atime, src_stat.st_mtime))
                if os.name == 'nt':
                    try:
                        set_creation_time_windows(webp_path, src_stat.st_ctime)
                    except Exception as win_err:
                        print(f"[WARNING] Failed to preserve creation timestamp for {webp_path.name}: {win_err}")
            except Exception as e:
                print(f"[WARNING] Failed to preserve timestamps for {webp_path.name}: {e}")
        
        if verbose:
            meta_status = "embedded" if has_metadata else "none found"
            preserve_status = ", times preserved" if preserve_timestamp else ""
            size_diff = src_size - dest_size
            pct = (size_diff / src_size * 100) if src_size > 0 else 0
            print(f"[CONVERTED] {png_path.name} -> {webp_path} (Metadata: {meta_status}{preserve_status}, Saved: {size_diff/1024:.1f}KB / {pct:.1f}%)")
            
        if delete_source:
            if not dry_run:
                os.remove(png_path)
                if verbose:
                    print(f"[DELETED] Original PNG: {png_path.name}")
                    
        return "success", src_size, dest_size
        
    except Exception as e:
        print(f"[ERROR] Failed to convert {png_path.name}: {e}")
        return "error", 0, 0

def format_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.2f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.2f} MB"

def main():
    parser = argparse.ArgumentParser(
        description="Migrate ComfyUI PNG images to WebP format, preserving visual workflow & prompt metadata in EXIF.",
        usage="%(prog)s [-h] [-q QUALITY] [-r] [-o] [-d] [--dry-run] [-v] [-f DESTINATION] [-w WORKERS] [-p] [path]"
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory path to scan for PNG files (defaults to current directory).'
    )
    parser.add_argument(
        '-q', '--quality',
        type=int,
        default=85,
        help='Compression quality (1-100, default: 85).'
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Scan subdirectories recursively.'
    )
    parser.add_argument(
        '-o', '--overwrite',
        action='store_true',
        help='Overwrite existing WebP files.'
    )
    parser.add_argument(
        '-d', '--delete-source',
        action='store_true',
        help='Delete original PNG files after successful conversion.'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be converted without modifying or deleting files.'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output detailing each file conversion.'
    )
    parser.add_argument(
        '-f', '--destination',
        type=str,
        default=None,
        help='Destination folder to save the output WebP images.'
    )
    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=None,
        help='Number of parallel worker processes to use (defaults to CPU count).'
    )
    parser.add_argument(
        '-p', '--preserve',
        action='store_true',
        help='Preserve original file modification and access times.'
    )
    
    args = parser.parse_args()
    
    target_dir = Path(args.path).resolve()
    if not target_dir.exists():
        print(f"Error: Path '{target_dir}' does not exist.")
        sys.exit(1)
    if not target_dir.is_dir():
        print(f"Error: Path '{target_dir}' is a file, not a directory.")
        sys.exit(1)
        
    destination_dir = None
    if args.destination:
        destination_dir = Path(args.destination).resolve()
        if destination_dir.exists() and not destination_dir.is_dir():
            print(f"Error: Destination path '{destination_dir}' is a file, not a directory.")
            sys.exit(1)
        
    pattern = "**/*.png" if args.recursive else "*.png"
    # Find all PNG files (case-insensitive)
    png_files = []
    for ext in ['*.png', '*.PNG']:
        png_files.extend(list(target_dir.rglob(ext) if args.recursive else target_dir.glob(ext)))
        
    # De-duplicate in case system paths are case-insensitive and match twice
    png_files = sorted(list(set(png_files)))
    png_files = [f.resolve() for f in png_files]
    
    total_files = len(png_files)
    if total_files == 0:
        print(f"No PNG files found in '{target_dir}'")
        return
        
    print(f"Found {total_files} PNG file(s) to process.")
    if args.dry_run:
        print("--- RUNNING IN DRY-RUN MODE (no files will be written/deleted) ---")
    if args.delete_source:
        print("--- WARNING: Source PNG files will be DELETED after successful conversion ---")
        
    stats = {
        'success': 0,
        'skipped_exists': 0,
        'dry_run': 0,
        'error': 0,
        'total_src_size': 0,
        'total_dest_size': 0
    }
    
    num_workers = args.workers
    if num_workers is None:
        try:
            # Default to a safe number of workers (max 4) to prevent Out-Of-Memory process termination on large image batches
            num_workers = min(4, multiprocessing.cpu_count())
        except NotImplementedError:
            num_workers = 1
    num_workers = max(1, num_workers)
    
    use_multiprocessing = num_workers > 1 and total_files > 1
    
    processed_files = set()
    pool_broken = False
    
    if use_multiprocessing:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from concurrent.futures.process import BrokenProcessPool
        print(f"Starting parallel migration using {num_workers} workers...")
        futures = {}
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            for png_path in png_files:
                webp_path = None
                if destination_dir:
                    relative_path = png_path.relative_to(target_dir)
                    webp_path = destination_dir / relative_path.with_suffix('.webp')
                    
                future = executor.submit(
                    convert_png_to_webp,
                    png_path,
                    quality=args.quality,
                    overwrite=args.overwrite,
                    delete_source=args.delete_source,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    webp_path=webp_path,
                    preserve_timestamp=args.preserve
                )
                futures[future] = png_path
                
            for idx, future in enumerate(as_completed(futures), start=1):
                png_path = futures[future]
                if not args.verbose:
                    print(f"Processing image {idx}/{total_files} ({png_path.name})...", end='\r')
                try:
                    status, src_sz, dest_sz = future.result()
                    processed_files.add(png_path)
                    stats[status] += 1
                    if status in ('success', 'dry_run'):
                        stats['total_src_size'] += src_sz
                        stats['total_dest_size'] += dest_sz
                except BrokenProcessPool:
                    print(f"\n[WARNING] Process pool broke while processing {png_path.name}. Switching to sequential fallback...")
                    pool_broken = True
                    break
                except Exception as e:
                    processed_files.add(png_path)
                    print(f"\n[ERROR] Process failed for {png_path.name}: {e}")
                    stats['error'] += 1
                    
        if pool_broken:
            # Cancel any remaining futures
            for f in futures:
                f.cancel()
                
    # If not using multiprocessing, or if the pool broke, process remaining files sequentially
    if not use_multiprocessing or pool_broken:
        remaining_files = [f for f in png_files if f not in processed_files]
        if pool_broken:
            print(f"Processing {len(remaining_files)} remaining file(s) sequentially...")
        for idx, png_path in enumerate(remaining_files, start=len(processed_files) + 1):
            if not args.verbose:
                # Print a simple progress indicator
                print(f"Processing image {idx}/{total_files} ({png_path.name})...", end='\r')
                
            webp_path = None
            if destination_dir:
                relative_path = png_path.relative_to(target_dir)
                webp_path = destination_dir / relative_path.with_suffix('.webp')
                
            status, src_sz, dest_sz = convert_png_to_webp(
                png_path,
                quality=args.quality,
                overwrite=args.overwrite,
                delete_source=args.delete_source,
                dry_run=args.dry_run,
                verbose=args.verbose,
                webp_path=webp_path,
                preserve_timestamp=args.preserve
            )
            
            stats[status] += 1
            if status in ('success', 'dry_run'):
                stats['total_src_size'] += src_sz
                stats['total_dest_size'] += dest_sz
            
    if not args.verbose:
        # Clear progress line
        print(" " * 80, end='\r')
        
    print("\nMigration Summary:")
    print(f"  Processed: {total_files} files")
    if stats['success'] > 0:
        print(f"  Converted successfully: {stats['success']}")
    if stats['skipped_exists'] > 0:
        print(f"  Skipped (already exists): {stats['skipped_exists']}")
    if stats['dry_run'] > 0:
        print(f"  Dry-run matches: {stats['dry_run']}")
    if stats['error'] > 0:
        print(f"  Errors encountered: {stats['error']}")
        
    if stats['success'] > 0 or stats['dry_run'] > 0:
        saved_bytes = stats['total_src_size'] - stats['total_dest_size']
        pct = (saved_bytes / stats['total_src_size'] * 100) if stats['total_src_size'] > 0 else 0
        
        mode_str = "Would save" if args.dry_run else "Saved"
        print(f"  Original size: {format_size(stats['total_src_size'])}")
        print(f"  WebP size: {format_size(stats['total_dest_size'])}")
        print(f"  {mode_str}: {format_size(saved_bytes)} ({pct:.1f}% reduction)")

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
