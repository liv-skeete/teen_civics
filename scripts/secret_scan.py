#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

# Base directory (repo root)
BASE_DIR = Path(__file__).resolve().parent.parent  # scripts/.. -> repo root

# Directories to skip
EXCLUDE_DIRS = {
    '.git', '.hg', '.svn', '.venv', 'venv', 'ENV', '__pycache__',
    'dist', 'build', '.tox', '.pytest_cache', 'htmlcov', '.idea',
    '.vscode', '.mypy_cache', '.ruff_cache', 'node_modules'
}

# File types to scan
INCLUDE_EXTS = {'.py', '.yml', '.yaml', '.json', '.ini', '.cfg', '.sh'}

# Files to skip (docs/examples)
EXCLUDE_FILE_REGEXES = [
    re.compile(r'.*\.md$', re.IGNORECASE),
    re.compile(r'.*\.example$', re.IGNORECASE),
    re.compile(r'^LICENSE$', re.IGNORECASE),
]

# Lines we explicitly allow (local ephemeral DBs in CI)
ALLOWLIST_LINE_REGEXES = [
    re.compile(r'postgres(ql)?://postgres:postgres@localhost:\d+/', re.IGNORECASE),
    re.compile(r'DATABASE_URL[^\n]*localhost', re.IGNORECASE),
]

# Patterns indicating likely secret leaks
PATTERNS = [
    # e.g., os.environ['DATABASE_URL'] = 'postgresql://user:pass@host:port/db'
    ('Hardcoded DATABASE_URL assignment',
     re.compile(r"os\.environ\[['\"]DATABASE_URL['\"]\]\s*=\s*['\"][^'\"]+['\"]")),

    # e.g., DATABASE_URL="postgresql://user:pass@host:port/db" (YAML/INI/SH/etc.)
    ('Hardcoded DATABASE_URL literal',
     re.compile(r"\bDATABASE_URL\b\s*[:=]\s*['\"][^'\"]+['\"]")),

    # Any URL with inline credentials to a non-localhost host
    ('URL with inline credentials to non-localhost',
     re.compile(r"[A-Za-z][A-Za-z0-9+\-.]*://[^/\s'\"@]+:[^/\s'\"@]+@(?!(localhost|127\.0\.0\.1|0\.0\.0\.0))",
               re.IGNORECASE)),

    # Private keys (should never be in repo)
    ('Private key block',
     re.compile(r"-----BEGIN (?:RSA |DSA |EC )?PRIVATE KEY-----")),

    # AWS Access Key ID (common high-value token)
    ('AWS Access Key ID',
     re.compile(r"AKIA[0-9A-Z]{16}")),
]

def is_excluded_file(rel_path: str) -> bool:
    name = os.path.basename(rel_path)
    for rx in EXCLUDE_FILE_REGEXES:
        if rx.match(rel_path) or rx.match(name):
            return True
    return False

def is_allowlisted_line(line: str) -> bool:
    for rx in ALLOWLIST_LINE_REGEXES:
        if rx.search(line):
            return True
    return False

def is_comment_line(rel_path: str, line: str) -> bool:
    """
    Treat leading comment lines as non-issues across supported file types.
    This avoids flagging example strings in comments (e.g., docs or scanner examples).
    """
    stripped = line.lstrip()
    if not stripped:
        return True  # ignore empty lines
    # Common comment prefixes across our scanned types: .py, .sh, .yml/.yaml, .ini/.cfg
    if stripped.startswith("#") or stripped.startswith(";") or stripped.startswith("//"):
        return True
    return False

def should_scan_file(path: Path) -> bool:
    return path.suffix.lower() in INCLUDE_EXTS

def scan():
    issues = []
    for root, dirs, files in os.walk(BASE_DIR):
        # prune dirs
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            fpath = Path(root) / fname
            rel = str(fpath.relative_to(BASE_DIR))
            if is_excluded_file(rel):
                continue
            if not should_scan_file(fpath):
                continue
            try:
                # Use a more robust reading approach to avoid pathlib issues
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception as e:
                print(f"Skipping unreadable file: {rel} ({e})", file=sys.stderr)
                continue
            lines = text.splitlines()
            for idx, line in enumerate(lines, start=1):
                # Skip empty, allowlisted, and comment lines
                if not line.strip() or is_allowlisted_line(line) or is_comment_line(rel, line):
                    continue
                for reason, rx in PATTERNS:
                    m = rx.search(line)
                    if not m:
                        continue
                    snippet = line.strip()

                    # Skip template strings or placeholders that are not secrets
                    if '{' in snippet and '}' in snippet:
                        continue
                    if 'user:password@host:port' in snippet or 'user:pass@host:port' in snippet:
                        continue

                    issues.append((rel, idx, reason, snippet))
    return issues

def main():
    issues = scan()
    if issues:
        print("Secret scan failed. Found potential hardcoded secrets:")
        for rel, idx, reason, snippet in issues:
            print(f"- {rel}:{idx} [{reason}] -> {snippet}")
        print("\nSee SECURITY.md for policy. Use src/load_env.load_env() and environment variables.")
        sys.exit(1)
    else:
        print("Secret scan passed. No potential hardcoded secrets found.")

if __name__ == '__main__':
    main()