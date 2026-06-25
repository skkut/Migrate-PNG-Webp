import os
import sys
import json
from pathlib import Path
from PIL import Image

import png2webp

# Hardcoded test folder path
TEST_DIR = Path(r"c:\Projects\Migrate-PNG-Webp\test_images")

def verify_webp_metadata(webp_path, original_prompt_raw, original_workflow_raw):
    """
    Opens the WebP file and compares its EXIF metadata with the expected cleaned versions of the original metadata.
    """
    # Generate the expected cleaned JSON objects
    expected_prompt_json = None
    if original_prompt_raw:
        expected_prompt_json = json.loads(png2webp.clean_metadata(original_prompt_raw))
        
    expected_workflow_json = None
    if original_workflow_raw:
        expected_workflow_json = json.loads(png2webp.clean_metadata(original_workflow_raw))
        
    with Image.open(webp_path) as img:
        exif = img.getexif()
        prompt_val = exif.get(png2webp.TAG_MAKE)
        workflow_val = exif.get(png2webp.TAG_IMAGE_DESCRIPTION)
        
        # Verify prompt metadata
        if expected_prompt_json is not None:
            assert prompt_val is not None, "Make tag (prompt) was expected but not found in WebP EXIF."
            if isinstance(prompt_val, bytes):
                prompt_val = prompt_val.decode('utf-8')
            assert prompt_val.startswith("prompt:"), "Prompt tag in WebP EXIF does not start with 'prompt:'"
            parsed_prompt = json.loads(prompt_val[7:])
            assert parsed_prompt == expected_prompt_json, "Extracted prompt JSON does not match expected cleaned prompt"
            print("    [OK] Verified Make EXIF tag contains expected cleaned prompt.")
        else:
            assert prompt_val is None, "Make tag (prompt) was found in WebP EXIF but no source prompt existed."
            
        # Verify workflow metadata
        if expected_workflow_json is not None:
            assert workflow_val is not None, "ImageDescription tag (workflow) was expected but not found in WebP EXIF."
            if isinstance(workflow_val, bytes):
                workflow_val = workflow_val.decode('utf-8')
            assert workflow_val.startswith("workflow:"), "Workflow tag in WebP EXIF does not start with 'workflow:'"
            parsed_workflow = json.loads(workflow_val[9:])
            assert parsed_workflow == expected_workflow_json, "Extracted workflow JSON does not match expected cleaned workflow"
            print("    [OK] Verified ImageDescription EXIF tag contains expected cleaned workflow.")
        else:
            assert workflow_val is None, "ImageDescription tag (workflow) was found in WebP EXIF but no source workflow existed."

def main():
    if not TEST_DIR.exists():
        TEST_DIR.mkdir(parents=True)
        print(f"\nCreated folder: {TEST_DIR.resolve()}")

    # Find all PNG files in the test directory
    png_files = []
    for ext in ['*.png', '*.PNG']:
        png_files.extend(list(TEST_DIR.glob(ext)))
        png_files.extend(list(TEST_DIR.glob("nested/" + ext)))
        
    png_files = sorted(list(set(png_files)))
    
    generated_mock_images = False
    if not png_files:
        print(f"\nNo PNG files found in: {TEST_DIR.resolve()}. Generating mock test images...")
        generated_mock_images = True
        
        # Create a nested directory to test recursive structure
        nested_dir = TEST_DIR / "nested"
        nested_dir.mkdir(exist_ok=True)
        
        # Define mock files to create
        # Format: (relative_path, prompt, workflow)
        mock_definitions = [
            ("test_all.png", '{"1": {"inputs": {"text": "hello"}}}', '{"extra_pnginfo": {"workflow": {"nodes": []}}}'),
            ("test_prompt_only.png", '{"1": {"inputs": {"text": "world"}}}', None),
            ("test_workflow_only.png", None, '{"extra_pnginfo": {"workflow": {"nodes": [{"id": 1}]}}}'),
            ("test_no_meta.png", None, None),
            ("test_large_base64.png", None, '{"extra_pnginfo": {"workflow": {"nodes": [{"id": 1, "widgets_values": ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="]}]}}}'),
            ("nested/test_nested.png", '{"1": {"inputs": {"text": "nested_image"}}}', '{"extra_pnginfo": {"workflow": {"nodes": [{"id": 2}]}}}')
        ]
        
        from PIL.PngImagePlugin import PngInfo
        for rel_path_str, prompt, workflow in mock_definitions:
            img_path = TEST_DIR / rel_path_str
            img = Image.new('RGB', (10, 10), color='blue')
            meta = PngInfo()
            if prompt is not None:
                meta.add_text('prompt', prompt)
            if workflow is not None:
                meta.add_text('workflow', workflow)
            img.save(img_path, 'PNG', pnginfo=meta)
            png_files.append(img_path)
            
        png_files = sorted(list(set(png_files)))
        print(f"Generated {len(png_files)} mock test images.")
        
    print(f"\nFound {len(png_files)} PNG files to test in '{TEST_DIR.name}' directory.")
    
    # -------------------------------------------------------------
    # Test 1: Standard conversion (outputs in same folder)
    # -------------------------------------------------------------
    print("\n--- Test 1: Standard Side-by-Side Conversion ---")
    success_count = 0
    for idx, png_path in enumerate(png_files, start=1):
        print(f"\n[{idx}/{len(png_files)}] Testing: {png_path.relative_to(TEST_DIR)}")
        webp_path = png_path.with_suffix('.webp')
        
        # Read the raw metadata from original PNG
        try:
            with Image.open(png_path) as img:
                original_prompt_raw = img.info.get('prompt')
                original_workflow_raw = img.info.get('workflow')
        except Exception as e:
            print(f"  [FAIL] Could not open/read original PNG: {e}")
            continue
            
        # Perform conversion
        status, src_sz, dest_sz = png2webp.convert_png_to_webp(
            png_path,
            quality=85,
            overwrite=True,
            delete_source=False,
            dry_run=False,
            verbose=False
        )
        
        if status != "success":
            print(f"  [FAIL] Conversion failed with status: {status}")
            continue
            
        if not webp_path.exists():
            print("  [FAIL] Conversion reported success, but WebP file does not exist.")
            continue
            
        # Verify metadata
        try:
            verify_webp_metadata(webp_path, original_prompt_raw, original_workflow_raw)
            print(f"  [SUCCESS] {png_path.name} converted and verified successfully.")
            success_count += 1
        except AssertionError as ae:
            print(f"  [FAIL] Metadata verification assertion failed: {ae}")
        except Exception as e:
            print(f"  [FAIL] Error verifying metadata: {e}")
            
    print(f"\nStandard Conversion Test: {success_count}/{len(png_files)} files passed validation.")
    
    # Clean up standard webp outputs so they don't interfere with next test
    for png_path in png_files:
        webp_path = png_path.with_suffix('.webp')
        if webp_path.exists():
            webp_path.unlink()
            
    # -------------------------------------------------------------
    # Test 2: Destination folder conversion
    # -------------------------------------------------------------
    print("\n--- Test 2: Destination Folder Conversion ---")
    dest_dir = TEST_DIR.parent / "test_images_dest"
    if dest_dir.exists():
        import shutil
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    dest_success_count = 0
    for idx, png_path in enumerate(png_files, start=1):
        # We need to replicate relative structure under dest_dir
        relative_path = png_path.relative_to(TEST_DIR)
        dest_webp_path = dest_dir / relative_path.with_suffix('.webp')
        
        print(f"\n[{idx}/{len(png_files)}] Testing destination mapping: {relative_path} -> {dest_webp_path.relative_to(dest_dir.parent)}")
        
        # Read raw metadata
        try:
            with Image.open(png_path) as img:
                original_prompt_raw = img.info.get('prompt')
                original_workflow_raw = img.info.get('workflow')
        except Exception as e:
            print(f"  [FAIL] Could not open/read original PNG: {e}")
            continue
            
        # Perform conversion with custom webp_path
        status, src_sz, dest_sz = png2webp.convert_png_to_webp(
            png_path,
            quality=85,
            overwrite=True,
            delete_source=False,
            dry_run=False,
            verbose=False,
            webp_path=dest_webp_path
        )
        
        if status != "success":
            print(f"  [FAIL] Conversion failed with status: {status}")
            continue
            
        if not dest_webp_path.exists():
            print(f"  [FAIL] Conversion reported success, but destination WebP file does not exist: {dest_webp_path}")
            continue
            
        # Verify metadata
        try:
            verify_webp_metadata(dest_webp_path, original_prompt_raw, original_workflow_raw)
            print(f"  [SUCCESS] {png_path.name} converted and verified in destination successfully.")
            dest_success_count += 1
        except AssertionError as ae:
            print(f"  [FAIL] Metadata verification assertion failed: {ae}")
        except Exception as e:
            print(f"  [FAIL] Error verifying metadata: {e}")
            
    print(f"\nDestination Conversion Test: {dest_success_count}/{len(png_files)} files passed validation.")
    
    # Clean up
    if dest_dir.exists():
        import shutil
        shutil.rmtree(dest_dir)
        print(f"\nRemoved temporary destination folder: {dest_dir.resolve()}")
        
    # -------------------------------------------------------------
    # Test 3: Multiprocessing CLI execution with preservation
    # -------------------------------------------------------------
    print("\n--- Test 3: Multiprocessing CLI Execution with Preservation ---")
    import subprocess
    dest_dir_cli = TEST_DIR.parent / "test_images_dest_cli"
    if dest_dir_cli.exists():
        import shutil
        shutil.rmtree(dest_dir_cli)
        
    cmd = [
        sys.executable,
        "png2webp.py",
        str(TEST_DIR),
        "-f", str(dest_dir_cli),
        "-r",
        "-w", "4",
        "-p",
        "-v"
    ]
    print(f"Running command: {' '.join(cmd)}")
    cli_result = subprocess.run(cmd, capture_output=True, text=True)
    print("Subprocess stdout output:")
    print(cli_result.stdout)
    if cli_result.stderr:
        print("Subprocess stderr output:")
        print(cli_result.stderr)
        
    # Verify outputs exist in the destination directory and check timestamps
    cli_success_count = 0
    cli_preserve_count = 0
    for png_path in png_files:
        relative_path = png_path.relative_to(TEST_DIR)
        dest_webp_path = dest_dir_cli / relative_path.with_suffix('.webp')
        if dest_webp_path.exists():
            cli_success_count += 1
            src_stat = png_path.stat()
            dest_stat = dest_webp_path.stat()
            mtime_diff = abs(dest_stat.st_mtime - src_stat.st_mtime)
            ctime_preserved = True
            ctime_diff = 0.0
            if os.name == 'nt':
                ctime_diff = abs(dest_stat.st_ctime - src_stat.st_ctime)
                ctime_preserved = ctime_diff < 0.1
                
            if mtime_diff < 0.1 and ctime_preserved:
                cli_preserve_count += 1
                ctime_str = f", ctime diff={ctime_diff:.4f}s" if os.name == 'nt' else ""
                print(f"    [OK] CLI preserved timestamps for {relative_path} (mtime diff={mtime_diff:.4f}s{ctime_str})")
            else:
                print(f"    [FAIL] CLI timestamps mismatch for {relative_path}: src_mtime={src_stat.st_mtime}, dest_mtime={dest_stat.st_mtime}, src_ctime={src_stat.st_ctime}, dest_ctime={dest_stat.st_ctime}")
            
    print(f"\nMultiprocessing CLI Test: {cli_success_count}/{len(png_files)} files processed, {cli_preserve_count}/{len(png_files)} preserved timestamps.")
    
    # Clean up dest_dir_cli
    if dest_dir_cli.exists():
        import shutil
        shutil.rmtree(dest_dir_cli)
        print(f"Removed temporary destination folder: {dest_dir_cli.resolve()}")
        
    # -------------------------------------------------------------
    # Test 4: Timestamp preservation unit test
    # -------------------------------------------------------------
    print("\n--- Test 4: Timestamp Preservation Unit Test ---")
    preserve_success_count = 0
    for idx, png_path in enumerate(png_files, start=1):
        webp_path = png_path.with_suffix('.preserve.webp')
        
        # Get source timestamps
        src_stat = png_path.stat()
        src_atime = src_stat.st_atime
        src_mtime = src_stat.st_mtime
        
        status, src_sz, dest_sz = png2webp.convert_png_to_webp(
            png_path,
            quality=85,
            overwrite=True,
            delete_source=False,
            dry_run=False,
            verbose=False,
            webp_path=webp_path,
            preserve_timestamp=True
        )
        
        if status != "success":
            print(f"  [FAIL] Conversion failed with status: {status}")
            continue
            
        if not webp_path.exists():
            print("  [FAIL] Conversion reported success, but WebP file does not exist.")
            continue
            
        # Get destination timestamps
        dest_stat = webp_path.stat()
        dest_atime = dest_stat.st_atime
        dest_mtime = dest_stat.st_mtime
        
        mtime_diff = abs(dest_mtime - src_mtime)
        ctime_preserved = True
        ctime_diff = 0.0
        if os.name == 'nt':
            ctime_diff = abs(dest_stat.st_ctime - src_stat.st_ctime)
            ctime_preserved = ctime_diff < 0.1
            
        if mtime_diff < 0.1 and ctime_preserved:
            ctime_str = f", diff ctime={ctime_diff:.4f}s" if os.name == 'nt' else ""
            print(f"  [OK] Timestamps preserved for {png_path.name} (diff mtime={mtime_diff:.4f}s{ctime_str})")
            preserve_success_count += 1
        else:
            print(f"  [FAIL] Timestamps NOT preserved for {png_path.name}. Source mtime: {src_mtime}, Dest mtime: {dest_mtime}. Source ctime: {src_stat.st_ctime}, Dest ctime: {dest_stat.st_ctime}")
            
        # Clean up
        if webp_path.exists():
            webp_path.unlink()
            
    print(f"\nTimestamp Preservation Test: {preserve_success_count}/{len(png_files)} files passed validation.")
        
    if generated_mock_images:
        # Clean up generated source images
        for png_path in png_files:
            if png_path.exists():
                png_path.unlink()
        nested_dir = TEST_DIR / "nested"
        if nested_dir.exists():
            nested_dir.rmdir()
        print(f"Cleaned up mock test images from {TEST_DIR.resolve()}")
        
    # Check overall status
    if (success_count == len(png_files) and 
        dest_success_count == len(png_files) and 
        cli_success_count == len(png_files) and 
        cli_preserve_count == len(png_files) and 
        preserve_success_count == len(png_files)):
        print("\nALL TESTS PASSED SUCCESSFULLY!")
    else:
        print("\nSOME TESTS FAILED!")
        sys.exit(1)

if __name__ == '__main__':
    main()
