#!/usr/bin/env python3
"""
Script to fix Git commit performance issues in the TeenCivics repository.

This script addresses common causes of slow Git commits:
1. Large tracked files (especially data/bills.db)
2. Corrupted Git index
3. Repository optimization issues
"""

import os
import subprocess
import sys
import shutil
from pathlib import Path

def run_command(command, cwd=None):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=cwd, 
            capture_output=True, 
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {command}")
        print(f"Error: {e.stderr}")
        return None

def check_git_status():
    """Check current Git status."""
    print("Checking Git status...")
    status = run_command("git status --porcelain")
    if status:
        print("Files currently staged or modified:")
        print(status)
    else:
        print("No changes detected.")
    return status

def optimize_git_index():
    """Rebuild the Git index to fix potential corruption."""
    print("Optimizing Git index...")
    
    # Backup current index
    index_path = ".git/index"
    backup_path = ".git/index.backup"
    
    if os.path.exists(index_path):
        print("Backing up current index...")
        shutil.copy2(index_path, backup_path)
        
        # Remove and rebuild index
        print("Removing current index...")
        os.remove(index_path)
        
        print("Rebuilding index...")
        run_command("git reset")
        print("Index rebuilt successfully.")
    else:
        print("No index file found.")

def optimize_repository():
    """Run Git maintenance commands."""
    print("Running Git maintenance...")
    
    # Garbage collection
    print("Running git gc...")
    run_command("git gc")
    
    # File system check
    print("Running git fsck...")
    run_command("git fsck")
    
    print("Repository optimization complete.")

def handle_large_files():
    """Handle large files that may be causing commit delays."""
    print("Checking for large files...")
    
    # Check if data/bills.db is tracked
    db_file = "data/bills.db"
    if os.path.exists(db_file):
        result = run_command(f"git ls-files {db_file}")
        if result:
            print(f"WARNING: {db_file} is tracked by Git.")
            print("This may be causing commit delays.")
            print("Consider adding '*.db' to .gitignore and removing the file from tracking.")
        else:
            print(f"{db_file} is not tracked by Git.")
    else:
        print(f"{db_file} does not exist.")

def update_gitignore():
    """Ensure database files are properly ignored."""
    gitignore_path = ".gitignore"
    
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as f:
            content = f.read()
        
        # Check if database patterns are already in .gitignore
        db_patterns = ["*.db", "*.sqlite", "*.sqlite3"]
        missing_patterns = []
        
        for pattern in db_patterns:
            if pattern not in content:
                missing_patterns.append(pattern)
        
        if missing_patterns:
            print("Updating .gitignore with database patterns...")
            with open(gitignore_path, 'a') as f:
                f.write("\n# Database files\n")
                for pattern in missing_patterns:
                    f.write(f"{pattern}\n")
            print("Updated .gitignore successfully.")
        else:
            print(".gitignore already contains database patterns.")
    else:
        print(".gitignore file not found.")

def main():
    """Main function to fix Git commit issues."""
    print("TeenCivics Git Commit Optimization Script")
    print("=" * 45)
    
    # Change to repository root if needed
    repo_root = run_command("git rev-parse --show-toplevel")
    if repo_root and repo_root != os.getcwd():
        print(f"Changing to repository root: {repo_root}")
        os.chdir(repo_root)
    
    # Check current status
    check_git_status()
    
    # Handle large files
    handle_large_files()
    
    # Update .gitignore
    update_gitignore()
    
    # Optimize Git index
    optimize_git_index()
    
    # Run repository maintenance
    optimize_repository()
    
    print("\nGit commit optimization complete!")
    print("\nTo commit your changes quickly, try:")
    print("  git add -A")
    print("  git commit --no-verify -m \"Your commit message\"")
    print("\nFor long-term performance, consider:")
    print("  git rm --cached data/bills.db  # If you want to stop tracking the database")
    print("  git commit -m \"Remove database file from tracking\"")

if __name__ == "__main__":
    main()