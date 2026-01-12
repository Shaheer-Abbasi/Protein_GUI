"""
Script to package local databases for S3 upload.

Usage:
    python package_databases.py                    # Package all configured databases
    python package_databases.py --list             # List available databases
    python package_databases.py --db swissprot     # Package specific database
    python package_databases.py --db refseq        # Package refseq (warning: large!)

This script:
1. Creates ZIP archives of database files
2. Calculates SHA256 checksums
3. Outputs the information needed to update the manifest
"""

import os
import sys
import zipfile
import hashlib
import json
import argparse
from datetime import datetime

# Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "s3_upload")
VERSION = datetime.now().strftime("%Y-%m-%d")

# Available databases to package
AVAILABLE_DATABASES = {
    "swissprot_blast": {
        "display_name": "SwissProt (BLAST)",
        "source_dir": os.path.join(PROJECT_ROOT, "blast_databases", "swissprot"),
        "output_name": "swissprot_blast.zip",
        "type": "blast",
        "db_name": "swissprot",
        "recommended_for_s3": True
    },
    "swissprot_mmseqs": {
        "display_name": "SwissProt (MMseqs2)",
        "source_dir": os.path.join(PROJECT_ROOT, "mmseqs_databases"),
        "output_name": "swissprot_mmseqs.zip",
        "type": "mmseqs",
        "db_name": "swissprot",
        "recommended_for_s3": True
    },
    "refseq_blast": {
        "display_name": "RefSeq Protein (BLAST)",
        "source_dir": os.path.join(PROJECT_ROOT, "blast_databases", "refseq_protein"),
        "output_name": "refseq_protein_blast.zip",
        "type": "blast",
        "db_name": "refseq_protein",
        "recommended_for_s3": False  # Too large for S3 starter pack
    },
    "refseq_mmseqs": {
        "display_name": "RefSeq Protein (MMseqs2)",
        "source_dir": os.path.join(PROJECT_ROOT, "mmseqs_databases"),
        "output_name": "refseq_protein_mmseqs.zip",
        "type": "mmseqs",
        "db_name": "custom_refseq_protein",
        "recommended_for_s3": False
    }
}


def calculate_sha256(filepath):
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192 * 1024), b''):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def format_size(size_bytes):
    """Format bytes as human-readable string"""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def package_blast_database(source_dir, output_zip):
    """Package a BLAST database into a ZIP file"""
    print(f"  Packaging BLAST database from {source_dir}")
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename in os.listdir(source_dir):
            filepath = os.path.join(source_dir, filename)
            if os.path.isfile(filepath):
                print(f"    Adding: {filename}")
                zf.write(filepath, filename)
    
    return output_zip


def package_mmseqs_database(source_dir, output_zip, db_name):
    """Package an MMseqs2 database into a ZIP file"""
    print(f"  Packaging MMseqs2 database '{db_name}' from {source_dir}")
    
    # MMseqs2 database files follow pattern: dbname, dbname.*, dbname_h, dbname_h.*
    prefixes = [db_name, f"{db_name}_h"]
    
    files_added = 0
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename in os.listdir(source_dir):
            filepath = os.path.join(source_dir, filename)
            if os.path.isfile(filepath):
                # Check if file belongs to this database
                for prefix in prefixes:
                    if filename == prefix or filename.startswith(f"{prefix}."):
                        print(f"    Adding: {filename}")
                        zf.write(filepath, filename)
                        files_added += 1
                        break
    
    if files_added == 0:
        print(f"  [WARNING] No files found for database '{db_name}'")
        os.remove(output_zip)
        return None
    
    return output_zip


def list_databases():
    """List all available databases"""
    print("\nAvailable databases to package:\n")
    print(f"{'ID':<20} {'Name':<30} {'Source Exists':<15} {'Recommended'}")
    print("-" * 80)
    
    for db_id, db_info in AVAILABLE_DATABASES.items():
        exists = os.path.exists(db_info["source_dir"])
        recommended = "Yes (small)" if db_info["recommended_for_s3"] else "No (large)"
        status = "Yes" if exists else "No"
        print(f"{db_id:<20} {db_info['display_name']:<30} {status:<15} {recommended}")
    
    print("\nUsage:")
    print("  python package_databases.py --db swissprot_blast")
    print("  python package_databases.py --db swissprot_blast swissprot_mmseqs")
    print("  python package_databases.py --all")


def package_database(db_id):
    """Package a single database"""
    if db_id not in AVAILABLE_DATABASES:
        print(f"[ERROR] Unknown database: {db_id}")
        print(f"Available: {', '.join(AVAILABLE_DATABASES.keys())}")
        return None
    
    db_info = AVAILABLE_DATABASES[db_id]
    source_dir = db_info["source_dir"]
    
    if not os.path.exists(source_dir):
        print(f"[SKIP] Source not found: {source_dir}")
        return None
    
    # Warn about large databases
    if not db_info["recommended_for_s3"]:
        print(f"\n[WARNING] {db_info['display_name']} is large and not recommended for S3 hosting.")
        print("Consider using the 'installer' distribution type instead.")
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("Skipped.")
            return None
    
    output_zip = os.path.join(OUTPUT_DIR, db_info["output_name"])
    
    print(f"\nPackaging: {db_info['display_name']}")
    
    if db_info["type"] == "blast":
        result = package_blast_database(source_dir, output_zip)
    elif db_info["type"] == "mmseqs":
        result = package_mmseqs_database(source_dir, output_zip, db_info["db_name"])
    else:
        print(f"[ERROR] Unknown database type: {db_info['type']}")
        return None
    
    if result is None:
        return None
    
    # Calculate stats
    file_size = os.path.getsize(output_zip)
    sha256 = calculate_sha256(output_zip)
    
    print(f"  [OK] Created: {output_zip}")
    print(f"  [OK] Size: {format_size(file_size)}")
    print(f"  [OK] SHA256: {sha256}")
    
    return {
        "id": db_id,
        "display_name": db_info["display_name"],
        "file": output_zip,
        "filename": db_info["output_name"],
        "size_bytes": file_size,
        "size_gb": round(file_size / (1024 * 1024 * 1024), 3),
        "sha256": sha256,
        "type": db_info["type"]
    }


def main():
    parser = argparse.ArgumentParser(description="Package databases for S3 upload")
    parser.add_argument("--list", action="store_true", help="List available databases")
    parser.add_argument("--db", nargs="+", help="Database IDs to package")
    parser.add_argument("--all", action="store_true", help="Package all recommended databases")
    
    args = parser.parse_args()
    
    if args.list:
        list_databases()
        return
    
    print("=" * 60)
    print("Database Packaging Script for S3 Upload")
    print("=" * 60)
    print(f"Version: {VERSION}")
    print(f"Output directory: {OUTPUT_DIR}")
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Determine which databases to package
    if args.db:
        db_ids = args.db
    elif args.all:
        # Package all that exist and are recommended
        db_ids = [
            db_id for db_id, info in AVAILABLE_DATABASES.items()
            if info["recommended_for_s3"] and os.path.exists(info["source_dir"])
        ]
    else:
        # Default: package recommended databases
        db_ids = [
            db_id for db_id, info in AVAILABLE_DATABASES.items()
            if info["recommended_for_s3"] and os.path.exists(info["source_dir"])
        ]
    
    if not db_ids:
        print("\nNo databases to package. Use --list to see available options.")
        return
    
    print(f"\nDatabases to package: {', '.join(db_ids)}")
    
    results = []
    for db_id in db_ids:
        result = package_database(db_id)
        if result:
            results.append(result)
    
    # Summary
    if results:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"\nFiles created in: {OUTPUT_DIR}")
        print(f"Version: {VERSION}\n")
        
        for r in results:
            print(f"  {r['id']}:")
            print(f"    File: {r['filename']}")
            print(f"    Size: {format_size(r['size_bytes'])}")
            print(f"    SHA256: {r['sha256']}")
            print()
        
        # Save results to JSON
        results_file = os.path.join(OUTPUT_DIR, "package_info.json")
        with open(results_file, 'w') as f:
            json.dump({
                "version": VERSION,
                "created": datetime.now().isoformat(),
                "packages": results
            }, f, indent=2)
        
        print(f"Package info saved to: {results_file}")
        
        # Print manifest snippet
        print("\n" + "=" * 60)
        print("MANIFEST SNIPPETS (copy to databases_manifest.json)")
        print("=" * 60)
        
        for r in results:
            tool = "blast" if r["type"] == "blast" else "mmseqs"
            db_folder = r["id"].replace("_blast", "").replace("_mmseqs", "")
            print(f'''
{{
  "id": "{r['id']}",
  "distribution": {{
    "type": "s3",
    "url": "https://sen-lab-protein-databases.s3.us-east-2.amazonaws.com/databases/{db_folder}/{VERSION}/{r['filename']}",
    "sha256": "{r['sha256']}",
    "compressed": true
  }}
}}''')
        
        print("\n" + "=" * 60)
        print("UPLOAD COMMANDS")
        print("=" * 60)
        print("\nUpload to S3 using AWS CLI:")
        for r in results:
            db_folder = r["id"].replace("_blast", "").replace("_mmseqs", "")
            print(f'aws s3 cp "{r["file"]}" s3://sen-lab-protein-databases/databases/{db_folder}/{VERSION}/{r["filename"]}')
    
    else:
        print("\nNo databases were packaged.")


if __name__ == "__main__":
    main()
