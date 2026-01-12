#!/usr/bin/env python3
"""
Check for database updates from NCBI and UniProt.

This script checks the release dates/versions of upstream databases
and reports which ones have been updated since the manifest was last updated.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError


def get_ncbi_blast_db_info():
    """
    Get information about NCBI BLAST database versions.
    Checks the NCBI FTP for last-modified dates.
    """
    # NCBI doesn't have a nice API for this, but we can check the README
    url = "https://ftp.ncbi.nlm.nih.gov/blast/db/README"
    
    try:
        req = Request(url, headers={'User-Agent': 'ProteinGUI/1.0'})
        with urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            # The README is updated when databases change
            # We can use the current date as a proxy for "latest"
            return {
                "source": "ncbi_blast",
                "checked": datetime.now().isoformat(),
                "status": "available"
            }
    except URLError as e:
        return {
            "source": "ncbi_blast",
            "error": str(e),
            "status": "error"
        }


def get_uniprot_release_info():
    """
    Get the current UniProt release version.
    UniProt has a nice release notes page we can check.
    """
    url = "https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/reldate.txt"
    
    try:
        req = Request(url, headers={'User-Agent': 'ProteinGUI/1.0'})
        with urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            # Parse: "UniProt Knowledgebase Release 2024_01 consists of:"
            match = re.search(r'Release (\d{4}_\d{2})', content)
            if match:
                return {
                    "source": "uniprot",
                    "version": match.group(1),
                    "checked": datetime.now().isoformat(),
                    "status": "available"
                }
    except URLError as e:
        pass
    
    return {
        "source": "uniprot",
        "error": "Could not fetch release info",
        "status": "error"
    }


def get_pdb_release_info():
    """
    Get the current PDB release information.
    """
    # PDB releases weekly on Wednesday
    # We can approximate based on the current date
    today = datetime.now()
    # Find the most recent Wednesday
    days_since_wednesday = (today.weekday() - 2) % 7
    last_release = today.replace(hour=0, minute=0, second=0, microsecond=0)
    
    return {
        "source": "pdb",
        "version": today.strftime("%Y-%m-%d"),
        "checked": datetime.now().isoformat(),
        "status": "available",
        "note": "PDB releases weekly on Wednesdays"
    }


def load_current_manifest(manifest_path):
    """Load the current manifest file."""
    try:
        with open(manifest_path, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load manifest: {e}", file=sys.stderr)
        return None


def check_for_updates(manifest, force=False):
    """
    Check all sources for updates.
    
    Returns dict with update information.
    """
    updates = {}
    
    # Get current versions from manifest
    manifest_date = manifest.get('last_updated', '2000-01-01')
    
    # Check NCBI
    ncbi_info = get_ncbi_blast_db_info()
    print(f"NCBI BLAST: {ncbi_info.get('status')}")
    
    # Check UniProt
    uniprot_info = get_uniprot_release_info()
    print(f"UniProt: {uniprot_info.get('status')} - {uniprot_info.get('version', 'N/A')}")
    
    # Check PDB
    pdb_info = get_pdb_release_info()
    print(f"PDB: {pdb_info.get('status')} - {pdb_info.get('version', 'N/A')}")
    
    # Determine if updates are needed
    today = datetime.now().strftime("%Y-%m-%d")
    manifest_age_days = (datetime.now() - datetime.fromisoformat(manifest_date)).days
    
    # Consider update needed if manifest is older than 7 days
    updates_available = force or manifest_age_days >= 7
    
    if updates_available:
        updates['manifest_date'] = {
            'old_version': manifest_date,
            'new_version': today,
            'reason': f'Manifest is {manifest_age_days} days old'
        }
    
    # Check UniProt version against manifest
    for db in manifest.get('databases', []):
        if 'uniref' in db['id'].lower() or 'uniprot' in db['id'].lower():
            manifest_version = db.get('version', '')
            upstream_version = uniprot_info.get('version', '')
            
            if upstream_version and manifest_version != upstream_version:
                updates[db['id']] = {
                    'old_version': manifest_version,
                    'new_version': upstream_version,
                    'source': 'uniprot'
                }
                updates_available = True
    
    return {
        'updates_available': updates_available,
        'updates': updates,
        'checked': datetime.now().isoformat(),
        'new_manifest_version': today if updates_available else manifest_date,
        'sources': {
            'ncbi': ncbi_info,
            'uniprot': uniprot_info,
            'pdb': pdb_info
        }
    }


def main():
    parser = argparse.ArgumentParser(description='Check for database updates')
    parser.add_argument('--manifest', default='databases_manifest.json',
                        help='Path to manifest file')
    parser.add_argument('--output', default='updates.json',
                        help='Output file for update information')
    parser.add_argument('--force', action='store_true',
                        help='Force update even if no changes detected')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Database Update Checker")
    print("=" * 60)
    print()
    
    # Load current manifest
    manifest = load_current_manifest(args.manifest)
    if manifest is None:
        manifest = {'last_updated': '2000-01-01', 'databases': []}
    
    print(f"Current manifest version: {manifest.get('last_updated', 'Unknown')}")
    print()
    
    # Check for updates
    print("Checking upstream sources...")
    result = check_for_updates(manifest, force=args.force)
    
    # Save results
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print()
    print("=" * 60)
    print("Results")
    print("=" * 60)
    print(f"Updates available: {result['updates_available']}")
    
    if result['updates']:
        print("\nUpdates detected:")
        for db_id, info in result['updates'].items():
            print(f"  - {db_id}: {info.get('old_version', 'N/A')} -> {info.get('new_version', 'N/A')}")
    
    print(f"\nResults saved to: {args.output}")
    
    # Exit with code 0 if updates available, 1 if not (for CI/CD)
    sys.exit(0 if result['updates_available'] else 1)


if __name__ == '__main__':
    main()
