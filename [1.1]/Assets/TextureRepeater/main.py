"""
TextureRepeater - Mirror-to-Repeat Texture Converter
=====================================================
Converts textures that rely on Mirror tiling (used in Blender) into textures
compatible with Repeat tiling (used in Roblox Studio).

Creates a 2x2 mirrored grid from each texture:
  ┌──────────┬──────────┐
  │ Original │ H-Flip   │
  ├──────────┼──────────┤
  │ V-Flip   │ HV-Flip  │
  └──────────┴──────────┘

When this new texture is set to "Repeat" in Roblox, it produces the same
seamless look as "Mirror" tiling in Blender.

Usage:
    python main.py                     # Process all PNGs in ../RR3
    python main.py --input ../RR3      # Specify input folder
    python main.py --backup            # Keep originals as .orig.png
    python main.py --output ./output   # Save mirrored textures to separate folder
    python main.py --dry-run           # Preview what would be processed
    python main.py --extensions png,jpg,tga  # Specify file types to process

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


def mirror_texture(image: Image.Image) -> Image.Image:
    """
    Create a 2x2 mirrored version of the input image.
    
    Layout:
      Top-left:     Original
      Top-right:    Flipped horizontally
      Bottom-left:  Flipped vertically
      Bottom-right: Flipped both horizontally and vertically
    
    This bakes the "Mirror" tiling pattern into the texture itself,
    so that "Repeat" tiling produces identical results.
    """
    w, h = image.size

    # Create the four quadrants
    original = image
    h_flip = image.transpose(Image.FLIP_LEFT_RIGHT)
    v_flip = image.transpose(Image.FLIP_TOP_BOTTOM)
    hv_flip = image.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM)

    # Assemble into 2x2 grid
    result = Image.new(image.mode, (w * 2, h * 2))
    result.paste(original, (0, 0))
    result.paste(h_flip, (w, 0))
    result.paste(v_flip, (0, h))
    result.paste(hv_flip, (w, h))

    return result


def find_textures(input_dir: Path, extensions: set) -> list:
    """Recursively find all texture files in the given directory."""
    textures = []
    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            ext = Path(filename).suffix.lower().lstrip(".")
            if ext in extensions:
                textures.append(Path(root) / filename)
    return sorted(textures)


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
        
        # Create mirrored version
        mirrored = mirror_texture(img)
        
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
        
        mirrored.save(out_path, **save_kwargs)
        
        new_size = mirrored.size
        msg = f"{original_size[0]}x{original_size[1]} -> {new_size[0]}x{new_size[1]}"
        return (str(rel_path), True, msg)
        
    except Exception as e:
        return (str(rel_path), False, str(e))


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
        help="Output directory for mirrored textures (default: overwrite in-place)"
    )
    parser.add_argument(
        "--backup", "-b",
        action="store_true",
        help="Keep original files as .orig.png before overwriting"
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
    
    if output_dir:
        print(f"Output: {output_dir}")
    else:
        mode = "in-place (with backup)" if args.backup else "in-place (overwrite)"
        print(f"Output: {mode}")
    
    print()
    
    # Dry run - just list files
    if args.dry_run:
        print("=== DRY RUN - No changes will be made ===\n")
        for tex in textures:
            rel = tex.relative_to(input_dir)
            try:
                img = Image.open(tex)
                w, h = img.size
                print(f"  [WOULD PROCESS] {rel}  ({w}x{h} -> {w*2}x{h*2})")
            except Exception as e:
                print(f"  [WOULD SKIP]    {rel}  (Error: {e})")
        print(f"\nTotal: {len(textures)} texture(s) would be processed")
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
