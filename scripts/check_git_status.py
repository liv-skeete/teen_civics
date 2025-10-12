#!/usr/bin/env python3
"""
Script to check Git status and help diagnose issues.
"""

import subprocess
import os
import sys

def run_command(command):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def main():
    print("Git Status Diagnostics")
    print("=" * 25)
    
    # Check current directory
    print(f"Current directory: {os.getcwd()}")
    
    # Check if we're in a Git repository
    stdout, stderr, code = run_command("git rev-parse --git-dir")
    if code != 0:
        print("Not in a Git repository!")
        return
    
    print("In Git repository")
    
    # Check branch status
    stdout, stderr, code = run_command("git branch --show-current")
    if code == 0:
        print(f"Current branch: {stdout}")
    
    # Check commits ahead/behind
    stdout, stderr, code = run_command("git status -sb")
    if code == 0:
        print("Branch status:")
        print(stdout)
    
    # Check recent commits
    stdout, stderr, code = run_command("git log --oneline -5")
    if code == 0:
        print("\nRecent commits:")
        print(stdout)
    
    # Check for untracked files
    stdout, stderr, code = run_command("git ls-files --others --exclude-standard")
    if code == 0 and stdout:
        print("\nUntracked files:")
        files = stdout.split('\n')
        for f in files[:10]:  # Show first 10
            print(f"  {f}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")

if __name__ == "__main__":
    main()