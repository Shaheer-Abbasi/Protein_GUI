# Remove mmseqs_databases from Git

## Steps to Remove from Git (Keep Local Files)

### 1. Remove from Git Tracking
```bash
git rm -r --cached mmseqs_databases/
```

**What this does:**
- `--cached` = Only removes from git, keeps local files
- `-r` = Recursive (removes folder and contents)

### 2. Commit the Changes
```bash
git add .gitignore
git commit -m "Remove mmseqs_databases from tracking, add to .gitignore"
```

### 3. Push to Remote (if you have one)
```bash
git push
```

## ✅ Done!

Your local `mmseqs_databases/` folder will stay on your computer, but won't be tracked by git anymore.

## 🔍 Verify It Worked

Check that it's no longer tracked:
```bash
git status
```

Should NOT show `mmseqs_databases/` as changed/staged.

---

## ⚠️ Note About Existing Commits

If you already pushed `mmseqs_databases/` to a remote repository:
- It will remain in git history
- Future changes won't be tracked
- Old commits still contain the files
- To completely remove from history (advanced): use `git filter-branch` or `BFG Repo Cleaner`
  - **Warning:** This rewrites history and requires force push

For most cases, just preventing future tracking is sufficient! ✅

