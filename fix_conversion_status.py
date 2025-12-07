"""Fix conversion_status.json to use Windows paths instead of WSL paths"""
import json
import os

status_file = "mmseqs_databases/conversion_status.json"

if os.path.exists(status_file):
    print(f"Found {status_file}")
    
    # Read current status
    with open(status_file, 'r') as f:
        status_data = json.load(f)
    
    print(f"Databases found: {list(status_data.get('databases', {}).keys())}")
    
    # Fix paths
    fixed = False
    for db_name, info in status_data.get('databases', {}).items():
        old_path = info.get('converted_path', '')
        
        # Check if it's a WSL path
        if old_path.startswith('/mnt/'):
            # Convert /mnt/e/... to E:\...
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
    
    if fixed:
        # Save updated status
        with open(status_file, 'w') as f:
            json.dump(status_data, f, indent=2)
        
        print("\n✓ Fixed! Paths have been updated to Windows format.")
        print(f"  Saved to: {status_file}")
    else:
        print("\nNo WSL paths found. File is already correct!")
else:
    print(f"File not found: {status_file}")
    print("Nothing to fix!")

