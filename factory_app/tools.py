from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
READABLE_ROOTS = {"docs", "change_requests", "campusflow", "tests", "runs"}
BINARY_SUFFIXES = {".db", ".png", ".jpg", ".jpeg", ".zip", ".pdf"}
MAX_READ_CHARS = 40_000
MAX_SEARCH_LINE_CHARS = 240


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
    items = [str(path.relative_to(REPO_ROOT)) for path in files]
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
    return {"ok": True, "path": str(rel), "content": text}


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

        rel_path = str(path.relative_to(REPO_ROOT))
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


def run_baseline_verification() -> dict:
    """Run an allowlisted deterministic baseline. No arbitrary shell input."""
    commands = [
        ["python", "-m", "pytest", "-q"],
        ["python", "-m", "ruff", "check", "campusflow", "tests", "factory_app", "scripts"],
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
    return {"ok": True, "path": str(path.relative_to(REPO_ROOT))}
