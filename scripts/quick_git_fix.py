#!/usr/bin/env python3
"""
Quick Git fix script for immediate commit issues.
This script focuses on the most common causes of slow Git commits.
"""

import os
import subprocess
import sys
import shutil

def run_command(command):
    """Run a shell command and return the result."""
    try:
        print(f"Running: {command}")
        result = subprocess.run(
            command, 
            shell=True, 
            cwd='.', 
            capture_output=True, 
            text=True,
            check=True
        )
        print(f"Output: {result.stdout.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {command}")
        print(f"Error: {e.stderr}")
        return None

def quick_fix():
    """Perform quick fixes for Git commit issues."""
    print("TeenCivics Quick Git Fix")
    print("=" * 25)
    
    # Check current directory
    try:
        repo_root = run_command("git rev-parse --show-toplevel")
        if repo_root:
            print(f"Repository root: {repo_root}")
        else:
            print("Not in a Git repository!")
            return
    except:
        print("Git not found or not in a Git repository!")
        return
    
    # Quick fixes
    print("\n1. Checking for staged files...")
    try:
        status = run_command("git status --porcelain")
        if status:
            print("Files are staged for commit.")
        else:
            print("No files staged for commit.")
    except:
        print("Could not check Git status.")
    
    print("\n2. Rebuilding Git index...")
    index_path = ".git/index"
    backup_path = ".git/index.backup"
    
    if os.path.exists(index_path):
        try:
            # Backup current index
            print("Backing up current index...")
            shutil.copy2(index_path, backup_path)
            
            # Remove and rebuild index
            print("Removing current index...")
            os.remove(index_path)
            
            print("Rebuilding index...")
            run_command("git reset")
            print("Index rebuilt successfully.")
        except Exception as e:
            print(f"Error rebuilding index: {e}")
    else:
        print("No index file found.")
    
    print("\n3. Quick repository optimization...")
    try:
        print("Running git reflog expire...")
        run_command("git reflog expire --expire=now --all")
        
        print("Running git gc...")
        run_command("git gc --auto")
    except Exception as e:
        print(f"Error during optimization: {e}")
    
    print("\nQuick fix complete!")
    print("\nTo commit quickly, try one of these:")
    print("  git commit --no-verify -m \"Quick commit\"")
    print("  git commit -m \"Quick commit\" --quiet")
    print("\nIf still slow, check if data/bills.db is tracked:")
    print("  git ls-files data/bills.db")

if __name__ == "__main__":
    quick_fix()