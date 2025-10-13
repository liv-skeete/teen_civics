# 🧠 Git Repository Recovery & Optimization — October 2025
**Author:** Liv (teencivics project)  
**Date:** October 12, 2025  
**Environment:** macOS  •  Git over SSH  •  VS Code

---

## ⚙️ Summary
After months of hanging Git operations (`git add`, `git commit`, `git push`, and `git gc` freezing), the repository was fully diagnosed and restored.  
A combination of **corrupted `.git` internals**, **stuck macOS credential helpers**, and **synced-folder interference (iCloud)** caused recurring lockups.  
By moving the project to a purely local directory and setting up clean SSH auth, Git operations now run instantly.

---

## 🧩 Timeline of Discovery

| Step | Action | Result / Notes |
|------|---------|----------------|
| **Diagnosis** | Used `iostat` + `ps aux` → ruled out disk issues and large repo. | CPU / disk normal. |
| **Suspected Cause 1** | Found `git-credential-osxkeychain` hanging. | Hanging authentication confirmed. |
| **Fix Attempt 1** | `pkill -f git-credential-osxkeychain` | Partial relief; intermittent hangs persisted. |
| **Suspected Cause 2** | Discovered repeated concurrent Git processes (VS Code & terminal). | Created leftover `.git/index.lock`. |
| **Fix Attempt 2** | Removed `.git/index.lock`; restarted Git. | Temporary improvement. |
| **Final Fix** | Performed safe backup → `mv .git .git_backup_<timestamp>` → fresh `git init` → `git fetch origin main` | Repo usable again but lingering issues. |
| **Permanent Fix** | Cloned repo fresh into `~/code/` (local, non‑synced). | `git add`, `git commit`, `git push` all instant. |

---

## 🧹 Root Causes

1. **Credential Helper Freeze**
   - macOS process `git-credential-osxkeychain` entered a deadlock.
   - Any HTTPS Git authentication waited indefinitely.
   - *Moved to SSH → eliminated Keychain dependency.*

2. **Concurrent Git Processes**
   - `git add` and VS Code’s background Git scanned simultaneously.
   - Left residual `.git/index.lock`, causing indefinite “waiting” states.

3. **iCloud/Spotlight Interference**
   - Original repo was nested under `~/Documents/` (iCloud‑synced).
   - Background sync and indexing occasionally held `.git/` open.

4. **Partial Resets & Garbage Collection**
   - Multiple interrupted `git gc`/`repack` created invalid pack indexes.
   - Periodic cleanup commands failed under locked state.

---

## 🔧 Final Working Setup

| Component | New Location / Command | Status |
|------------|------------------------|---------|
| **Repo path** | `~/code/teencivics` | Local ✓ (not synced) |
| **Remote** | `git@github.com:liv-skeete/teen_civics.git` | SSH ✓ |
| **Editor** | VS Code | Works; Git integration stable |
| **Test** | `git add . && git commit -m "chore: quick index-lock test"` | Instant ✅ |

---

## ⚡ Prevention Checklist

### 🔄 Git Hygiene
- Run **one Git command at a time** (avoid simultaneous terminal & VS Code commits).
- Before retrying a hung operation:  
  ```bash
  ls .git/*.lock
  rm -f .git/index.lock
  ```
- Never `kill -9` a running `git gc` mid‑process.

### ☁ Sync & Filesystem
- Keep active repos outside:  
  - `~/Documents/`, `~/Desktop/`, `iCloud Drive`, Dropbox, Google Drive.
- Use a local development folder like `~/code/`.

### 🔐 Authentication
- Prefer **SSH keys** over HTTPS (avoids Keychain latency).
- If switching back to HTTPS and it hangs:  
  ```bash
  pkill -f git-credential-osxkeychain
  ```

### 🧭 Periodic Maintenance
```bash
git fsck           # check for corrupt objects
git gc --prune=now # clean up
```

### 🧰 Optional Helper Alias
```bash
alias gitfix='pkill -f git && rm -f .git/*.lock; git gc --prune=now'
```

---

## ✅ Current Verified State (Oct 12 2025)
| Test | Result |
|------|---------|
| `git status` | Instant ✅ |
| `git add .` | Instant ✅ |
| `git commit` | Instant ✅ |
| `git push` (SSH) | Completed instantly ✅ |
| `rsync`/`mv` performance | Normal ✅ |
| Locks present | None ✅ |

---

## 💡 Lessons Learned
1. **Sync drives ≠ dev drives** — keep code local.  
2. **Stuck credential helpers** can mimic network issues.  
3. **VS Code background Git** can conflict with terminal Git.  
4. **Concurrent commands** are the #1 cause of persistent `.lock` files.  
5. A fresh clone is sometimes *faster than endless surgery on `.git/`*.

---

## 🏁 Final Snapshot
```bash
cd ~/code/teencivics
time git status
# 0.03s — lightning fast ⚡
```

---

**Everything is stable. Repo healthy. Workflow fast.**  
🎉 *teencivics is officially out of Git jail.*