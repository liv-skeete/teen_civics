# Git Best Practices for the TeenCivics Repository

To maintain a healthy and performant Git repository, please follow these best practices. These guidelines are designed to prevent the kind of corruption and slowdowns we have experienced.

## 1. Do Not Commit Large Binary Files

**The Problem:** The primary cause of our Git issues was tracking the `data/bills.db` SQLite database file. Git is designed for text files, not large, frequently changing binary files. Tracking binary files bloats the repository size and makes every `git` command slow.

**The Solution:**
- **Never commit `.db`, `.sqlite3`, `.log`, or other large binary files.**
- The `.gitignore` file has been updated to explicitly ignore these files. Do not remove these rules.
- For local development, your `data/bills.db` file will exist on your machine but will not be tracked by Git.
- For production (like in GitHub Actions), use a managed database service (e.g., PostgreSQL on Heroku, Neon, etc.). The `DATABASE_URL` environment variable should be used to connect to the appropriate database.

## 2. Avoid Concurrent Git Operations

**The Problem:** Running `git` commands in multiple terminals at the same time, or having VS Code's background Git processes run during a manual `git` command, can cause lock files (`index.lock`) and corrupt the repository.

**The Solution:**
- **Run one Git command at a time.** Wait for a command to finish before starting another.
- **Close VS Code during complex Git operations.** If you need to perform a complex rebase or use a script to clean the repository, close VS Code first to prevent it from interfering.
- **Use the `--no-verify` flag for commits if you suspect hooks are causing issues:** `git commit --no-verify -m "Your message"`

## 3. How to Recover from a Corrupted State

If your repository becomes slow or `git` commands start hanging, it is likely corrupted. Here is a safe recovery process:

1.  **Backup Your Local Changes:** Before running any recovery commands, copy any uncommitted work to a safe location outside the project directory (e.g., `/tmp/` or your Desktop).

2.  **Kill All Git Processes:**
    ```bash
    pkill -f "git"
    ```

3.  **Clean the `.git` Directory:**
    ```bash
    rm -f .git/index.lock .git/index
    ```

4.  **Reset to Match GitHub:**
    ```bash
    git reset --hard origin/main
    ```

5.  **Restore Your Backed-up Changes:** Copy your saved files back into the project directory.

6.  **Commit and Push:**
    ```bash
    git add .
    git commit -m "Your clear commit message"
    git push
    ```

By following these practices, we can keep the repository fast, healthy, and reliable for everyone.