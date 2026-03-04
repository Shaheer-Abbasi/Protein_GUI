"""Fix conversion_status.json to normalize paths for the current platform"""
import json
import os
import sys

status_file = "mmseqs_databases/conversion_status.json"

if os.path.exists(status_file):
    print(f"Found {status_file}")

    with open(status_file, 'r') as f:
        status_data = json.load(f)

    print(f"Databases found: {list(status_data.get('databases', {}).keys())}")

    fixed = False
    for db_name, info in status_data.get('databases', {}).items():
        old_path = info.get('converted_path', '')

        if sys.platform == 'win32':
            # On Windows, convert WSL paths to Windows paths
            if old_path.startswith('/mnt/'):
                parts = old_path[5:].split('/', 1)
                if len(parts) >= 2:
                    drive_letter = parts[0].upper()
                    path_rest = parts[1].replace('/', '\\')
                    new_path = f"{drive_letter}:\\{path_rest}"

                    print(f"  {db_name}:")
                    print(f"    Old: {old_path}")
                    print(f"    New: {new_path}")

                    info['converted_path'] = new_path
                    fixed = True
        else:
            # On macOS/Linux, convert Windows paths to native paths
            if '\\' in old_path or (len(old_path) >= 2 and old_path[1] == ':'):
                # Strip drive letter and convert backslashes
                path = old_path.replace('\\', '/')
                if len(path) >= 2 and path[1] == ':':
                    path = path[2:]

                new_path = os.path.normpath(path)
                print(f"  {db_name}:")
                print(f"    Old: {old_path}")
                print(f"    New: {new_path}")

                info['converted_path'] = new_path
                fixed = True
            elif old_path.startswith('/mnt/'):
                # WSL path on non-Windows; strip /mnt/x prefix
                parts = old_path[5:].split('/', 1)
                if len(parts) >= 2:
                    new_path = '/' + parts[1]
                    print(f"  {db_name}:")
                    print(f"    Old: {old_path}")
                    print(f"    New: {new_path}")

                    info['converted_path'] = new_path
                    fixed = True

    if fixed:
        with open(status_file, 'w') as f:
            json.dump(status_data, f, indent=2)

        print(f"\nFixed! Paths have been updated for {'Windows' if sys.platform == 'win32' else 'this platform'}.")
        print(f"  Saved to: {status_file}")
    else:
        print("\nNo path fixes needed. File is already correct!")
else:
    print(f"File not found: {status_file}")
    print("Nothing to fix!")
