from __future__ import annotations

import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
READABLE_ROOTS = {"docs", "change_requests", "campusflow", "tests", "runs"}
CODER_WRITABLE_ROOTS = {"campusflow", "tests"}
TEST_WRITABLE_ROOTS = {"tests"}
WRITABLE_SUFFIXES = {".py"}
BINARY_SUFFIXES = {".db", ".png", ".jpg", ".jpeg", ".zip", ".pdf"}
MAX_READ_CHARS = 40_000
MAX_SEARCH_LINE_CHARS = 240
SAFE_GIT_REF_RE = re.compile(r"^[A-Za-z0-9._/~^-]+$")
TEST_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)\s*\(", re.MULTILINE)

# Optional plan-scoped allowlist set by the orchestrator during CoderAgent execution.
_CODER_ALLOWED_PATHS: set[str] | None = None


@contextmanager
def scoped_coder_paths(allowed_paths: set[str] | None):
    """Restrict write_coder_file to an explicit set of POSIX repo-relative paths."""
    global _CODER_ALLOWED_PATHS
    previous = _CODER_ALLOWED_PATHS
    _CODER_ALLOWED_PATHS = (
        {p.strip().lstrip("./").replace("\\", "/") for p in allowed_paths}
        if allowed_paths is not None
        else None
    )
    try:
        yield
    finally:
        _CODER_ALLOWED_PATHS = previous


def _safe_repo_path(relative_path: str) -> Path:
    candidate = (REPO_ROOT / relative_path).resolve()
    if REPO_ROOT not in candidate.parents and candidate != REPO_ROOT:
        raise ValueError("path escapes repository")
    return candidate


def _iter_allowlisted_files(prefix: str = "") -> tuple[list[Path], str | None]:
    """Resolve and list non-hidden files under an allowlisted read-only area."""
    clean_prefix = prefix.strip().strip("/")
    if clean_prefix:
        top = clean_prefix.split("/", 1)[0]
        if top not in READABLE_ROOTS:
            return [], f"read not allowed under {top!r}"
        try:
            root = _safe_repo_path(clean_prefix)
        except ValueError as exc:
            return [], str(exc)
    else:
        root = REPO_ROOT

    if not root.exists():
        return [], "path does not exist"

    candidates = [root] if root.is_file() else sorted(root.rglob("*"))
    files: list[Path] = []
    for path in candidates:
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT)
        if not clean_prefix and rel.parts[0] not in READABLE_ROOTS:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        files.append(path)
    return files, None


def list_repo_files(prefix: str = "") -> dict:
    """List files under an allowlisted read-only area."""
    files, error = _iter_allowlisted_files(prefix)
    if error is not None:
        return {"ok": False, "error": error}
    items = [path.relative_to(REPO_ROOT).as_posix() for path in files]
    return {"ok": True, "files": items[:250]}


def read_repo_file(relative_path: str) -> dict:
    """Read UTF-8 text from an allowlisted repository area."""
    try:
        path = _safe_repo_path(relative_path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    rel = path.relative_to(REPO_ROOT)
    if not rel.parts or rel.parts[0] not in READABLE_ROOTS:
        return {"ok": False, "error": "read not allowed for this path"}
    if not path.is_file():
        return {"ok": False, "error": "file does not exist"}
    if path.suffix.lower() in BINARY_SUFFIXES:
        return {"ok": False, "error": "binary file not supported"}
    text = path.read_text(encoding="utf-8")
    if len(text) > MAX_READ_CHARS:
        text = text[:MAX_READ_CHARS] + "\n...[TRUNCATED]..."
    return {"ok": True, "path": rel.as_posix(), "content": text}


def search_repo(
    pattern: str,
    prefix: str = "",
    max_results: int = 50,
    case_sensitive: bool = False,
) -> dict:
    """Search UTF-8 text lines under an allowlisted read-only area.

    Tries `pattern` as a regular expression and falls back to literal matching
    if the expression is not a valid regex.
    """
    if not pattern:
        return {"ok": False, "error": "pattern must not be empty"}

    files, error = _iter_allowlisted_files(prefix)
    if error is not None:
        return {"ok": False, "error": error}

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error:
        regex = re.compile(re.escape(pattern), flags)

    limit = max(1, min(max_results, 100))
    matches: list[dict] = []
    truncated = False

    for path in files:
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        rel_path = path.relative_to(REPO_ROOT).as_posix()
        for line_no, line in enumerate(content.splitlines(), start=1):
            if not regex.search(line):
                continue
            snippet = line.strip()
            if len(snippet) > MAX_SEARCH_LINE_CHARS:
                snippet = snippet[:MAX_SEARCH_LINE_CHARS] + "..."
            matches.append({"path": rel_path, "line": line_no, "text": snippet})
            if len(matches) >= limit:
                truncated = True
                return {
                    "ok": True,
                    "pattern": pattern,
                    "matches": matches,
                    "truncated": truncated,
                }

    return {"ok": True, "pattern": pattern, "matches": matches, "truncated": truncated}


def _validate_write_path(
    relative_path: str, allowed_roots: set[str]
) -> tuple[Path | None, str | None]:
    try:
        path = _safe_repo_path(relative_path)
    except ValueError as exc:
        return None, str(exc)
    rel = path.relative_to(REPO_ROOT)
    if not rel.parts or rel.parts[0] not in allowed_roots:
        return None, f"write not allowed for {rel.as_posix()!r}"
    if any(part.startswith(".") for part in rel.parts):
        return None, "writing hidden paths is not allowed"
    if path.suffix.lower() not in WRITABLE_SUFFIXES:
        return None, f"file extension {path.suffix!r} is not writable"
    return path, None


def write_coder_file(relative_path: str, content: str) -> dict:
    """Write a Python file strictly under campusflow/ or tests/ (plan-scoped when active)."""
    path, error = _validate_write_path(relative_path, CODER_WRITABLE_ROOTS)
    if error is not None or path is None:
        return {"ok": False, "error": error}

    rel_posix = path.relative_to(REPO_ROOT).as_posix()
    if _CODER_ALLOWED_PATHS is not None and rel_posix not in _CODER_ALLOWED_PATHS:
        return {
            "ok": False,
            "error": (
                f"path {rel_posix!r} is outside the approved implementation plan "
                f"(allowed: {sorted(_CODER_ALLOWED_PATHS)})"
            ),
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": rel_posix, "bytes": len(content.encode("utf-8"))}


def write_test_file(relative_path: str, content: str) -> dict:
    """Write or extend a test file strictly under tests/ without removing existing tests."""
    path, error = _validate_write_path(relative_path, TEST_WRITABLE_ROOTS)
    if error is not None or path is None:
        return {"ok": False, "error": error}

    rel_posix = path.relative_to(REPO_ROOT).as_posix()
    if path.exists():
        existing_tests = set(TEST_DEF_RE.findall(path.read_text(encoding="utf-8")))
        new_tests = set(TEST_DEF_RE.findall(content))
        removed = existing_tests - new_tests
        if removed:
            return {
                "ok": False,
                "error": f"cannot remove existing tests: {sorted(removed)}",
            }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": rel_posix, "bytes": len(content.encode("utf-8"))}


def git_diff_readonly(base_ref: str = "HEAD") -> dict:
    """Return read-only git diff and status for product/test files."""
    ref = base_ref.strip() or "HEAD"
    if ref.startswith("-") or not SAFE_GIT_REF_RE.match(ref):
        return {"ok": False, "error": f"invalid git ref {base_ref!r}"}

    diff_proc = subprocess.run(
        ["git", "diff", ref, "--", "campusflow", "tests"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    status_proc = subprocess.run(
        ["git", "status", "--short", "--", "campusflow", "tests"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if diff_proc.returncode != 0:
        return {"ok": False, "error": diff_proc.stderr.strip() or "git diff failed"}

    diff_text = diff_proc.stdout
    if len(diff_text) > MAX_READ_CHARS:
        diff_text = diff_text[:MAX_READ_CHARS] + "\n...[TRUNCATED]..."
    return {
        "ok": True,
        "base_ref": ref,
        "status": status_proc.stdout.strip(),
        "diff": diff_text,
    }


def run_verification() -> dict:
    """Run allowlisted deterministic verification (pytest + ruff). No arbitrary shell input."""
    commands = [
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "ruff", "check", "campusflow", "tests", "factory_app", "scripts"],
    ]
    results = []
    all_ok = True
    for command in commands:
        completed = subprocess.run(
            command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=120, check=False
        )
        all_ok = all_ok and completed.returncode == 0
        results.append({
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-6000:],
            "stderr": completed.stderr[-3000:],
        })
    return {"ok": all_ok, "results": results}


def run_baseline_verification() -> dict:
    """Backward-compatible alias for run_verification."""
    return run_verification()


def write_run_evidence(change_id: str, filename: str, content: str) -> dict:
    """Write only evidence files under runs/<CR-ID>/; never product code."""
    if not change_id.startswith("CR-"):
        return {"ok": False, "error": "change_id must start with CR-"}
    if "/" in filename or "\\" in filename or not filename.endswith((".md", ".json", ".txt")):
        return {"ok": False, "error": "invalid evidence filename"}
    folder = REPO_ROOT / "runs" / change_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path.relative_to(REPO_ROOT).as_posix()}
