#!/usr/bin/env python3
"""
File removal utility for enterprise cleanup
"""

from pathlib import Path


def remove_files_from_list(file_list_path: str):
    """Remove files listed in a text file."""
    removed_count = 0
    not_found_count = 0

    with open(file_list_path) as f:
        files_to_remove = [line.strip() for line in f if line.strip()]

    print(f"Processing {len(files_to_remove)} files for removal...")

    for file_path in files_to_remove:
        # Convert Windows paths to Unix paths if needed
        file_path = file_path.replace("\\", "/")
        path = Path(file_path)

        try:
            if path.exists():
                if path.is_file():
                    path.unlink()
                    print(f"Removed: {file_path}")
                    removed_count += 1
                elif path.is_dir():
                    import shutil

                    shutil.rmtree(path)
                    print(f"Removed directory: {file_path}")
                    removed_count += 1
            else:
                print(f"Not found: {file_path}")
                not_found_count += 1
        except Exception as e:
            print(f"Error removing {file_path}: {e}")

    print("\nSummary:")
    print(f"  Files removed: {removed_count}")
    print(f"  Files not found: {not_found_count}")
    print(f"  Total processed: {len(files_to_remove)}")


if __name__ == "__main__":
    remove_files_from_list("tools/cleanup/files_to_remove.txt")
