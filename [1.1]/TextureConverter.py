"""
TextureRepeater - V-Flip Texture Converter
==========================================
Converts textures that rely on Mirror tiling (used in Blender) into textures
compatible with Repeat tiling (used in Roblox Studio).

Applies a vertical flip to each texture so that when set to "Repeat" in
Roblox, it produces the same seamless look as "Mirror" tiling in Blender.

Usage:
    python TextureConverter.py                     # Process all PNGs in ../RR3
    python TextureConverter.py --input ../RR3      # Specify input folder
    python TextureConverter.py --backup            # Keep originals as .orig.png
    python TextureConverter.py --output ./output   # Save flipped textures to separate folder
    python TextureConverter.py --dry-run           # Preview what would be processed
    python TextureConverter.py --extensions png,jpg,tga  # Specify file types to process
    python TextureConverter.py --restore -i ../RR3 # Restore originals from .orig backups

Requirements:
    pip install Pillow
"""

import os
import sys
import time
import shutil
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install it with:")
    print("  pip install Pillow")
    sys.exit(1)


def flip_texture(image: Image.Image) -> Image.Image:
    """
    Vertically flip the input image.
    
    This converts a Mirror-tiled texture into one that tiles correctly
    with Repeat mode in Roblox Studio.
    """
    return image.transpose(Image.FLIP_TOP_BOTTOM)


def find_textures(input_dir: Path, extensions: set) -> list:
    """Recursively find all texture files in the given directory."""
    textures = []
    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            ext = Path(filename).suffix.lower().lstrip(".")
            if ext in extensions:
                textures.append(Path(root) / filename)
    return sorted(textures)


def is_already_processed(
    texture_path: Path,
    input_dir: Path,
    output_dir: Path | None,
    backup: bool,
) -> bool:
    """
    Check if a texture has already been processed.
    
    - With --output: skip if the file already exists in the output directory.
    - With --backup: skip if a .orig backup file already exists (means it was processed before).
    """
    if output_dir:
        rel_path = texture_path.relative_to(input_dir)
        return (output_dir / rel_path).exists()
    elif backup:
        backup_path = texture_path.with_suffix(f".orig{texture_path.suffix}")
        return backup_path.exists()
    return False


def process_texture(
    texture_path: Path,
    input_dir: Path,
    output_dir: Path | None,
    backup: bool,
) -> tuple[str, bool, str]:
    """
    Process a single texture file.
    
    Returns: (relative_path, success, message)
    """
    rel_path = texture_path.relative_to(input_dir)
    
    try:
        # Open the image
        img = Image.open(texture_path)
        original_size = img.size
        
        # Create flipped version
        flipped = flip_texture(img)
        
        # Determine output path
        if output_dir:
            out_path = output_dir / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = texture_path
            # Backup original if requested
            if backup:
                backup_path = texture_path.with_suffix(f".orig{texture_path.suffix}")
                if not backup_path.exists():
                    shutil.copy2(texture_path, backup_path)
        
        # Save with same format and quality settings
        save_kwargs = {}
        if texture_path.suffix.lower() in (".jpg", ".jpeg"):
            save_kwargs["quality"] = 95
            save_kwargs["subsampling"] = 0
        elif texture_path.suffix.lower() == ".png":
            save_kwargs["compress_level"] = 6
        
        flipped.save(out_path, **save_kwargs)
        
        msg = f"{original_size[0]}x{original_size[1]} flipped"
        return (str(rel_path), True, msg)
        
    except Exception as e:
        return (str(rel_path), False, str(e))


def find_backup_files(input_dir: Path) -> list:
    """Recursively find all .orig.* backup files in the given directory."""
    backups = []
    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            # Match pattern like "texture.orig.png"
            parts = filename.rsplit(".", 2)
            if len(parts) >= 3 and parts[-2] == "orig":
                backups.append(Path(root) / filename)
    return sorted(backups)


def restore_backups(input_dir: Path, dry_run: bool) -> None:
    """
    Restore original files from .orig backups.
    
    Finds all .orig.* files, removes the processed version, and renames
    the backup back to the original filename.
    """
    print(f"Scanning for backups: {input_dir}")
    backups = find_backup_files(input_dir)
    
    if not backups:
        print("No .orig backup files found. Nothing to restore.")
        return
    
    print(f"Found {len(backups)} backup(s) to restore")
    print()
    
    if dry_run:
        print("=== DRY RUN - No changes will be made ===\n")
        for backup_path in backups:
            # Derive the original name: remove .orig from the suffix chain
            original_name = backup_path.name.replace(".orig.", ".", 1)
            original_path = backup_path.parent / original_name
            rel = backup_path.relative_to(input_dir)
            print(f"  [WOULD RESTORE] {rel} -> {original_name}")
        print(f"\nTotal: {len(backups)} file(s) would be restored")
        return
    
    restored = 0
    failed = 0
    for backup_path in backups:
        original_name = backup_path.name.replace(".orig.", ".", 1)
        original_path = backup_path.parent / original_name
        rel = backup_path.relative_to(input_dir)
        try:
            # Remove the processed file if it exists
            if original_path.exists():
                original_path.unlink()
            # Rename backup to original
            backup_path.rename(original_path)
            restored += 1
            print(f"  [RESTORED] {rel} -> {original_name}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL]     {rel}  ({e})")
    
    print(f"\n{'='*60}")
    print(f"  Restored: {restored}")
    print(f"  Failed:   {failed}")
    print(f"  Total:    {len(backups)}")
    
    if failed > 0:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Convert Mirror-tiled textures to Repeat-compatible textures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        help="Input directory containing textures (default: ../RR3 relative to this script)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory for flipped textures (default: overwrite in-place)"
    )
    parser.add_argument(
        "--backup", "-b",
        action="store_true",
        help="Keep original files as .orig.png before overwriting"
    )
    parser.add_argument(
        "--restore", "-r",
        action="store_true",
        help="Restore original files from .orig backups (requires --input)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be processed without making changes"
    )
    parser.add_argument(
        "--extensions", "-e",
        type=str,
        default="png",
        help="Comma-separated list of file extensions to process (default: png)"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)"
    )
    
    args = parser.parse_args()
    
    # Resolve input directory
    script_dir = Path(__file__).parent.resolve()
    if args.input:
        input_dir = Path(args.input).resolve()
    else:
        input_dir = (script_dir / ".." / "RR3").resolve()
    
    if not input_dir.exists():
        print(f"ERROR: Input directory not found: {input_dir}")
        sys.exit(1)
    
    # Handle --restore mode
    if args.restore:
        if not args.input:
            print("ERROR: --restore requires --input to specify the directory to restore")
            sys.exit(1)
        restore_backups(input_dir, args.dry_run)
        return
    
    # Resolve output directory
    output_dir = Path(args.output).resolve() if args.output else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse extensions
    extensions = {ext.strip().lower().lstrip(".") for ext in args.extensions.split(",")}
    
    # Find all textures
    print(f"Scanning: {input_dir}")
    print(f"Extensions: {', '.join(sorted(extensions))}")
    textures = find_textures(input_dir, extensions)
    
    if not textures:
        print("No texture files found!")
        sys.exit(0)
    
    print(f"Found {len(textures)} texture(s)")
    
    # Filter out already-processed textures
    skipped = [t for t in textures if is_already_processed(t, input_dir, output_dir, args.backup)]
    textures = [t for t in textures if not is_already_processed(t, input_dir, output_dir, args.backup)]
    
    if skipped:
        print(f"Skipping {len(skipped)} already-processed texture(s)")
    
    if not textures:
        print("All textures already processed. Nothing to do.")
        sys.exit(0)
    
    if output_dir:
        print(f"Output: {output_dir}")
    else:
        mode = "in-place (with backup)" if args.backup else "in-place (overwrite)"
        print(f"Output: {mode}")
    
    print()
    
    # Dry run - just list files
    if args.dry_run:
        print("=== DRY RUN - No changes will be made ===\n")
        if skipped:
            for tex in skipped:
                rel = tex.relative_to(input_dir)
                print(f"  [SKIP]           {rel}  (already processed)")
        for tex in textures:
            rel = tex.relative_to(input_dir)
            try:
                img = Image.open(tex)
                w, h = img.size
                print(f"  [WOULD PROCESS] {rel}  ({w}x{h} -> v-flip)")
            except Exception as e:
                print(f"  [WOULD SKIP]    {rel}  (Error: {e})")
        print(f"\nTotal: {len(textures)} texture(s) would be processed, {len(skipped)} skipped")
        return
    
    # Process textures
    start_time = time.time()
    success_count = 0
    fail_count = 0
    
    print("Processing textures...\n")
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_texture, tex, input_dir, output_dir, args.backup
            ): tex
            for tex in textures
        }
        
        for i, future in enumerate(as_completed(futures), 1):
            rel_path, success, msg = future.result()
            
            if success:
                success_count += 1
                status = "OK"
            else:
                fail_count += 1
                status = "FAIL"
            
            progress = f"[{i}/{len(textures)}]"
            print(f"  {progress:>10}  [{status}]  {rel_path}  ({msg})")
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  Processed: {success_count}")
    print(f"  Failed:    {fail_count}")
    print(f"  Total:     {len(textures)}")
    
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
