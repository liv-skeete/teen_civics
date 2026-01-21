#!/usr/bin/env python3
"""
Repository cleanup script to optimize Git performance.

This script performs various cleanup operations to improve Git performance:
1. Removes unnecessary files
2. Optimizes Git storage
3. Checks for large files
4. Provides recommendations for better performance
"""

import os
import subprocess
import sys
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

def find_large_files():
    """Find large files in the repository."""
    print("Finding large files in the repository...")
    
    # Find large objects in the Git database
    large_objects = run_command("git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '/^blob/ {print substr($0, index($0, $4))}' | sort -n -k 2 | tail -10")
    
    if large_objects:
        print("Large objects in repository:")
        print(large_objects)
    else:
        print("No large objects found.")

def cleanup_git_files():
    """Clean up unnecessary Git files."""
    print("Cleaning up Git files...")
    
    # Clean untracked files
    print("Removing untracked files...")
    run_command("git clean -fd")
    
    # Prune remote tracking branches
    print("Pruning remote tracking branches...")
    run_command("git remote prune origin")
    
    print("Git file cleanup complete.")

def optimize_storage():
    """Optimize Git storage."""
    print("Optimizing Git storage...")
    
    # Repack objects
    print("Repacking objects...")
    run_command("git repack -ad")
    
    # Remove unreachable objects
    print("Removing unreachable objects...")
    run_command("git gc --prune=now")
    
    print("Storage optimization complete.")

def check_reflog():
    """Check and clean reflog if needed."""
    print("Checking reflog size...")
    
    reflog_entries = run_command("git reflog expire --expire=now --all")
    if reflog_entries:
        print("Reflog entries cleaned.")
    else:
        print("No reflog entries to clean.")

def main():
    """Main function to cleanup repository."""
    print("TeenCivics Repository Cleanup Script")
    print("=" * 38)
    
    # Change to repository root if needed
    repo_root = run_command("git rev-parse --show-toplevel")
    if repo_root and repo_root != os.getcwd():
        print(f"Changing to repository root: {repo_root}")
        os.chdir(repo_root)
    
    # Find large files
    find_large_files()
    
    # Cleanup Git files
    cleanup_git_files()
    
    # Optimize storage
    optimize_storage()
    
    # Check reflog
    check_reflog()
    
    print("\nRepository cleanup complete!")
    print("\nRecommendations:")
    print("1. If commits are still slow, consider using Git LFS for large files")
    print("2. Run this script periodically to maintain good performance")
    print("3. Consider squashing old commits to reduce repository size")
    print("4. Use shallow clones for CI/CD environments")

if __name__ == "__main__":
    main()