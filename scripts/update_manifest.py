#!/usr/bin/env python3
"""
Update the databases manifest with new version information.

This script reads update information from check_database_updates.py
and updates the manifest file with new dates and versions.
"""

import argparse
import json
import sys
from datetime import datetime


def load_json(filepath):
    """Load a JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading {filepath}: {e}", file=sys.stderr)
        return None


def save_json(filepath, data):
    """Save data to a JSON file."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def update_manifest(manifest, updates_info):
    """
    Update manifest with new version information.
    
    Args:
        manifest: Current manifest dict
        updates_info: Update information from check script
    
    Returns:
        Updated manifest dict
    """
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Update manifest metadata
    old_version = manifest.get('version', '1.0.0')
    version_parts = old_version.split('.')
    
    # Increment patch version
    try:
        version_parts[2] = str(int(version_parts[2]) + 1)
    except (IndexError, ValueError):
        version_parts = ['1', '0', '1']
    
    manifest['version'] = '.'.join(version_parts)
    manifest['last_updated'] = today
    
    # Update individual databases based on updates_info
    updates = updates_info.get('updates', {})
    sources = updates_info.get('sources', {})
    
    for db in manifest.get('databases', []):
        db_id = db['id']
        
        # Check if this database has a specific update
        if db_id in updates:
            update_info = updates[db_id]
            if 'new_version' in update_info:
                db['version'] = update_info['new_version']
                db['last_updated'] = today
                print(f"  Updated {db_id}: {update_info.get('old_version')} -> {update_info['new_version']}")
        
        # Update NCBI databases with today's date (they update continuously)
        elif db.get('distribution', {}).get('installer_kind') == 'ncbi_blast_update':
            # Only update the last_updated field, not the version
            # since we don't know the exact NCBI version
            db['last_updated'] = today
        
        # Update UniProt/UniRef databases
        elif 'uniref' in db_id.lower() or 'uniprot' in db_id.lower():
            uniprot_info = sources.get('uniprot', {})
            if uniprot_info.get('version'):
                db['version'] = uniprot_info['version']
                db['last_updated'] = today
    
    return manifest


def main():
    parser = argparse.ArgumentParser(description='Update database manifest')
    parser.add_argument('--manifest', default='databases_manifest.json',
                        help='Path to manifest file')
    parser.add_argument('--updates', default='updates.json',
                        help='Path to updates info file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show changes without saving')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Manifest Updater")
    print("=" * 60)
    print()
    
    # Load files
    manifest = load_json(args.manifest)
    updates_info = load_json(args.updates)
    
    if manifest is None:
        print("Error: Could not load manifest", file=sys.stderr)
        sys.exit(1)
    
    if updates_info is None:
        print("Error: Could not load updates info", file=sys.stderr)
        sys.exit(1)
    
    print(f"Current manifest version: {manifest.get('version')}")
    print(f"Updates available: {updates_info.get('updates_available')}")
    print()
    
    # Update manifest
    print("Applying updates...")
    updated_manifest = update_manifest(manifest, updates_info)
    
    print()
    print(f"New manifest version: {updated_manifest.get('version')}")
    print(f"New last_updated: {updated_manifest.get('last_updated')}")
    
    if args.dry_run:
        print("\n[DRY RUN] Changes not saved.")
        print("\nUpdated manifest would be:")
        print(json.dumps(updated_manifest, indent=2)[:500] + "...")
    else:
        save_json(args.manifest, updated_manifest)
        print(f"\nManifest saved to: {args.manifest}")
    
    print("\nDone!")


if __name__ == '__main__':
    main()
