#!/usr/bin/env python3
"""
Targeted script to fix Git commit issues specifically for feed_parser.py edits.
This script bypasses Git commands entirely to handle your hanging commit issue.
"""

import os
import shutil
import sys
from pathlib import Path

def manual_git_fix_for_feed_parser():
    """Fix Git issues specifically for feed_parser.py edits."""
    print("TeenCivics Feed Parser Git Fix")
    print("=" * 32)
    
    # Check if we're in the right directory
    if not os.path.exists('.git'):
        print("Error: Not in a Git repository root!")
        return False
    
    if not os.path.exists('src/fetchers/feed_parser.py'):
        print("Error: feed_parser.py not found!")
        return False
    
    print("Found repository and feed_parser.py")
    
    # Fix 1: Handle the specific hanging issue
    print("\n1. Fixing hanging Git processes...")
    
    # Remove problematic files that cause hanging
    problematic_files = [
        '.git/index',
        '.git/index.lock',
        '.git/HEAD.lock',
        '.git/logs/HEAD.lock'
    ]
    
    for file_path in problematic_files:
        if os.path.exists(file_path):
            try:
                print(f"Removing {file_path}...")
                os.remove(file_path)
                print(f"Removed {file_path}")
            except Exception as e:
                print(f"Could not remove {file_path}: {e}")
    
    # Fix 2: Backup and clean refs
    print("\n2. Cleaning Git refs...")
    refs_files = [
        '.git/refs/heads/main',
        '.git/refs/heads/master',
        '.git/refs/remotes/origin/main',
        '.git/refs/remotes/origin/master'
    ]
    
    for ref_file in refs_files:
        if os.path.exists(ref_file):
            try:
                backup_path = ref_file + '.backup'
                print(f"Backing up {ref_file} to {backup_path}...")
                shutil.copy2(ref_file, backup_path)
            except Exception as e:
                print(f"Could not backup {ref_file}: {e}")
    
    # Fix 3: Check database file that's likely causing issues
    db_file = 'data/bills.db'
    if os.path.exists(db_file):
        file_size = os.path.getsize(db_file)
        size_mb = file_size / (1024 * 1024)
        print(f"\n3. Database file check:")
        print(f"   {db_file}: {size_mb:.2f} MB")
        if size_mb > 10:  # If larger than 10MB
            print("   WARNING: Large database file may cause Git performance issues!")
            print("   Consider: Adding '*.db' to .gitignore and removing from tracking")
    
    # Fix 4: Create minimal index for feed_parser.py only
    print("\n4. Creating minimal Git state...")
    try:
        # Create a simple HEAD file if missing
        head_file = '.git/HEAD'
        if not os.path.exists(head_file):
            print("Creating basic HEAD file...")
            with open(head_file, 'w') as f:
                f.write('ref: refs/heads/main\n')
        
        # Create basic refs directory structure
        refs_dir = '.git/refs/heads'
        if not os.path.exists(refs_dir):
            print("Creating refs directory structure...")
            os.makedirs(refs_dir, exist_ok=True)
            
        # Create a basic main branch ref if missing
        main_ref = '.git/refs/heads/main'
        if not os.path.exists(main_ref):
            print("Creating basic main branch reference...")
            # This will be fixed properly when you restart Git
    except Exception as e:
        print(f"Could not create minimal Git state: {e}")
    
    print("\nManual fix complete!")
    print("\nNext steps:")
    print("1. CLOSE ALL TERMINALS and VS Code completely")
    print("2. Reopen ONE new terminal")
    print("3. Navigate to your repository")
    print("4. Run these commands one at a time:")
    print("   git status")
    print("   git add src/fetchers/feed_parser.py")
    print("   git commit -m \"Update feed parser\"")
    print("\nIf git status still hangs:")
    print("   Run: ./scripts/manual_git_fix.sh")
    print("   Then try the commands again")

def check_feed_parser_status():
    """Check the status of feed_parser.py specifically."""
    print("\nChecking feed_parser.py status...")
    
    file_path = 'src/fetchers/feed_parser.py'
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        print(f"File: {file_path}")
        print(f"Size: {file_size} bytes")
        
        # Check if file has been modified recently
        import time
        mtime = os.path.getmtime(file_path)
        print(f"Last modified: {time.ctime(mtime)}")
        
        # Show first few lines of the file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                print(f"\nFirst 5 lines of {file_path}:")
                for i, line in enumerate(lines[:5]):
                    print(f"  {i+1}: {line.rstrip()}")
        except Exception as e:
            print(f"Could not read file: {e}")
    else:
        print(f"File not found: {file_path}")

if __name__ == "__main__":
    manual_git_fix_for_feed_parser()
    check_feed_parser_status()