---
name: releasing-to-pypi
description: Use when committing code changes that will be tagged and released to PyPI, before creating any git commits, to ensure lint, version bump, tag placement, and changelog are all correct in one shot
---

# Releasing to PyPI

## Overview

A release to PyPI in this project requires **all steps completed atomically before pushing**. The publish workflow triggers on GitHub Release creation and checks out the **tag's commit** — if that commit has wrong versions, stale lint, or missing changelog, the release fails and cannot be re-uploaded to PyPI (immutable filenames).

**Core principle:** The tag must point to a commit where every file is release-ready. Work backwards from that constraint.

## When to Use

- Committing code that will be tagged for release
- Bumping versions for a new PyPI publish
- Creating any git tag prefixed with `v`

## The Checklist

**MANDATORY: Execute every step in order. Do not skip. Do not reorder.**

### Step 1: Lint BEFORE Committing

```bash
ruff check protocol/ core/ adapters/
```

If lint fails, fix it. **Never commit code that fails lint** — fixing lint after commit requires either amend (breaks protected branches) or an extra commit (splits changes, tag placement becomes error-prone).

### Step 2: Run ALL Tests BEFORE Committing

```bash
# Protocol tests
pytest protocol/tests/ --timeout=30

# Core tests (excluding on-chain)
pytest core/tests/ --timeout=30 -m "not devnet and not localnet and not mainnet"

# Adapter tests
cd adapters/mcp && pytest tests/ --timeout=30 && cd ../..
cd adapters/client_mcp && pytest tests/ --timeout=30 && cd ../..
```

All tests must pass. Do not commit with known failures.

### Step 3: Version Bump — ALL 10 Files in ONE Commit

Determine the next version. Check existing tags:

```bash
git tag -l 'v*' --sort=-v:refname | head -5
```

Update **all 10 files** in a single commit:

| # | File | Field | Notes |
|---|------|-------|-------|
| 1 | `protocol/pyproject.toml` | `version = "X.Y.Z"` | |
| 2 | `protocol/open402/__init__.py` | `__version__ = "X.Y.Z"` | ⚠️ Easy to forget |
| 3 | `core/pyproject.toml` | `version = "X.Y.Z"` | |
| 4 | `core/ag402_core/__init__.py` | `__version__ = "X.Y.Z"` | ⚠️ Easy to forget |
| 5 | `adapters/mcp/pyproject.toml` | `version = "X.Y.Z"` | |
| 6 | `adapters/mcp/ag402_mcp/__init__.py` | `__version__ = "X.Y.Z"` | ⚠️ Easy to forget |
| 7 | `adapters/client_mcp/pyproject.toml` | `version = "X.Y.Z"` | |
| 8 | `adapters/client_mcp/ag402_client_mcp/__init__.py` | `__version__ = "X.Y.Z"` | ⚠️ Easy to forget |
| 9 | `adapters/client_mcp/tests/test_server.py` | `assert __version__ == "X.Y.Z"` | ⚠️ Test will fail in CI if missed |
| 10 | `CHANGELOG.md` | Add `## [X.Y.Z]` section at top | |

**Verification command** — run this after editing to catch misses:

```bash
grep -r '"0\.1\.' protocol/pyproject.toml protocol/open402/__init__.py \
  core/pyproject.toml core/ag402_core/__init__.py \
  adapters/mcp/pyproject.toml adapters/mcp/ag402_mcp/__init__.py \
  adapters/client_mcp/pyproject.toml adapters/client_mcp/ag402_client_mcp/__init__.py \
  adapters/client_mcp/tests/test_server.py
```

All lines must show the same version. If any differ → STOP and fix.

**Never split version bump and code changes into separate commits before tagging.** The tag must land on a commit that has both the code changes AND the correct version numbers.

### Step 4: Update Documentation

Check and update test counts / feature descriptions in:

| File | What to check |
|------|---------------|
| `README.md` | Test count badge, config env var table, feature descriptions |
| `SECURITY.md` | Test totals, security feature list |
| `CHANGELOG.md` | New version section with correct date and changes |

### Step 5: Check for Sensitive / Internal Files

**CRITICAL**: Never commit internal planning docs or secrets.

```bash
# Verify .gitignore excludes internal docs
grep '开源发布行动计划' .gitignore  # Must be present

# Verify no secrets in staged files
git diff --cached --name-only | xargs grep -l 'PRIVATE_KEY\|ghp_\|sk-' 2>/dev/null
# Must return empty
```

### Step 6: Tag the FINAL Commit

```bash
git tag -a vX.Y.Z -m "vX.Y.Z: short description"
```

**The tag MUST point to the commit containing the version bump.** Verify:

```bash
git log --oneline -1 vX.Y.Z
# Must show the version bump commit, NOT an earlier commit
```

### Step 7: Push Commit + Tag Together

```bash
git push -u origin main && git push origin vX.Y.Z
```

### Step 8: Create GitHub Release (TRIGGERS PyPI Publish)

**This is the step that actually publishes to PyPI.** The `publish.yml` workflow triggers on `release: types: [published]`, NOT on tag push. Pushing a tag alone does NOT publish to PyPI.

```bash
gh release create vX.Y.Z --title "vX.Y.Z — Short description" --notes "$(cat <<'EOF'
## What's Changed

- Feature 1
- Feature 2
- ...

**Full Changelog**: https://github.com/AetherCore-Dev/ag402/blob/main/CHANGELOG.md
EOF
)"
```

After creating the release, verify the workflow triggered:

```bash
gh run list --workflow=publish.yml --limit=1
```

## Mistakes This Skill Prevents

| Mistake | Consequence | Prevention |
|---------|-------------|------------|
| Commit code, then fix lint separately | Extra commit; tag placed on wrong commit | Step 1: lint before commit |
| Forget `__init__.py` versions | `__version__` mismatches `pyproject.toml`; import shows wrong version; test fails in CI | Step 3: all 10 files + verification command |
| Forget test assertion version | `test_server.py::test_package_version` fails in CI → release blocked | Step 3: file #9 in the checklist |
| Tag on code commit, version bump in later commit | CI checks out tag → builds old version → PyPI rejects duplicate filename | Step 3+6: version bump + tag on same commit |
| Push tag but skip `gh release create` | **PyPI publish never triggers** — `publish.yml` fires on `release: [published]`, not on tag push | Step 8: always create GitHub Release |
| Commit internal docs (开源发布行动计划.md) | Internal planning docs leak to public repo | Step 5: verify .gitignore + check staged files |
| Forget CHANGELOG.md | Release notes incomplete | Step 3: CHANGELOG in same commit |
| Forget to update README/SECURITY.md | Stale test counts, missing env vars | Step 4: documentation checklist |
| `git push --force` on protected branch | Push rejected; requires extra fixup commits | Never amend pushed commits; get it right first time |
| Tag points to wrong commit | CI builds wrong version; PyPI upload fails with "File already exists" | Step 6: verify tag target |

## Red Flags — STOP and Recheck

- About to `git commit` but haven't run `ruff check` → STOP
- About to `git tag` but version bump is in a different commit → STOP
- `grep` verification shows mixed version numbers → STOP
- About to `git push --force` on main → STOP (protected branch)
- About to `gh release create` but `git log --oneline -1 vX.Y.Z` doesn't show version bump → STOP
- About to `git commit --amend` on an already-pushed commit → STOP
- `git diff --cached` shows `开源发布行动计划.md` or other internal files → STOP
- Pushed tag but didn't run `gh release create` → STOP (PyPI won't publish)

## Quick Reference: Ideal Single-Shot Flow

```bash
# 1. Lint
ruff check protocol/ core/ adapters/

# 2. Test (all 4 packages)
pytest protocol/tests/ --timeout=30
pytest core/tests/ --timeout=30 -m "not devnet and not localnet and not mainnet"
(cd adapters/mcp && pytest tests/ --timeout=30)
(cd adapters/client_mcp && pytest tests/ --timeout=30)

# 3. Bump versions (all 10 files) + update docs + update CHANGELOG
#    Then verify:
grep -r '"X\.Y\.Z"' protocol/pyproject.toml protocol/open402/__init__.py \
  core/pyproject.toml core/ag402_core/__init__.py \
  adapters/mcp/pyproject.toml adapters/mcp/ag402_mcp/__init__.py \
  adapters/client_mcp/pyproject.toml adapters/client_mcp/ag402_client_mcp/__init__.py \
  adapters/client_mcp/tests/test_server.py

# 4. Check no internal files staged
git diff --cached --name-only  # Should NOT include 开源发布行动计划.md

# 5. Commit
git add <specific files> && git commit -m "chore: release vX.Y.Z — description"

# 6. Tag the version-bumped commit
git tag -a vX.Y.Z -m "vX.Y.Z: description"

# 7. Push together
git push -u origin main && git push origin vX.Y.Z

# 8. Create GitHub Release (THIS triggers PyPI publish)
gh release create vX.Y.Z --title "vX.Y.Z — Description" --notes "..."

# 9. Verify publish workflow triggered
gh run list --workflow=publish.yml --limit=1
```

## Git Remote Configuration

When pushing to GitHub, use the authenticated HTTPS URL:

```bash
git remote set-url origin https://<PAT>@github.com/AetherCore-Dev/ag402.git
git config user.name "AetherCoreDev"
git config user.email "aethercore.dev@proton.me"
```
