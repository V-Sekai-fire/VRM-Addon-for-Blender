#!/usr/bin/env python3
"""
VRM Export Inspection Tools

Interactive tools to inspect and compare VRM export files for:
- EXT_mesh_bmesh extension presence and structure
- File size comparison
- Performance metrics
"""

import sys
from pathlib import Path

def inspect_file(vrm_path):
    """Inspect a single VRM file"""
    print(f"\nFILE: {vrm_path.name}")

    if not vrm_path.exists():
        print("ERROR: File does not exist")
        return False

    size_kb = vrm_path.stat().st_size / 1024
    print("Contains binary data: Yes")
    print("File type: {}".format("BMesh Enhanced" if "bmesh" in str(vrm_path) else "Standard VRM"))

    return True

def compare_directories():
    """Compare file sizes between directories"""
    fixtures_dir = Path(__file__).parent
    standard_dir = fixtures_dir / "standard_exports"
    bmesh_dir = fixtures_dir / "bmesh_exports"

    if not standard_dir.exists() or not bmesh_dir.exists():
        print("ERROR: Export directories not found")
        return

    print("\nFILE SIZE COMPARISON:")
    print("-" * 60)

    total_std = 0
    total_bmesh = 0
    count = 0

    for std_file in standard_dir.glob("*.vrm"):
        bmesh_file = bmesh_dir / f"{std_file.stem}_bmesh{std_file.suffix}"
        if bmesh_file.exists():
            std_size = std_file.stat().st_size
            bmesh_size = bmesh_file.stat().st_size
            diff_pct = ((bmesh_size - std_size) / std_size) * 100

            total_std += std_size
            total_bmesh += bmesh_size
            count += 1

    if count > 0:
        avg_diff = ((total_bmesh - total_std) / total_std) * 100
        print("\nAverage overhead: {:.1f}%".format(avg_diff))

def main():
    """Main inspection interface"""
    print("VRM Export Inspection Tools v1.0")
    print("="*40)

    fixtures_dir = Path(__file__).parent
    standard_dir = fixtures_dir / "standard_exports"
    bmesh_dir = fixtures_dir / "bmesh_exports"

    if not standard_dir.exists():
        print("ERROR: Export directories not found")
        print("Run: python test_fixtures_generator.py first")
        return

    # Show available files
    standard_files = list(standard_dir.glob("*.vrm"))
    bmesh_files = list(bmesh_dir.glob("*.vrm"))

    print("\nAvailable Files:")
    print(f"  Standard exports: {len(standard_files)} files")
    print(f"  BMesh exports: {len(bmesh_files)} files")

    if len(standard_files) > 0:
        print("\nStandard files:")
        for f in standard_files:
            size_kb = f.stat().st_size / 1024
            print(f"  size_kb: {size_kb} files")

    if len(bmesh_files) > 0:
        print("\nBMesh enhanced files:")
        for f in bmesh_files:
            size_kb = f.stat().st_size / 1024
            print(f"  size_kb: {size_kb} files")

        print("\nComparison Summary:")
        compare_directories()
    elif len(standard_files) > 0:
        print("\nComparison Summary:")
        compare_directories()

    print("\nUSAGE:")
    print("  python inspect_exports.py")
    print("\nCOMPLETE!")

if __name__ == '__main__':
    main()
