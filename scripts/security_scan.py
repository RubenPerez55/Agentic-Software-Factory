"""Deterministic Security Gate scanners (secrets, SAST, SCA).

Runs locally with zero billing and degrades transparently if optional CLI
scanners (`semgrep`, `pip-audit`) are not installed on PATH.

Usage:
  uv run python scripts/security_scan.py
  uv run python scripts/security_scan.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("google_vertex_key", re.compile(r"AQ\.[0-9A-Za-z_-]{30,}")),
    ("github_token", re.compile(r"gh[pousr]_[0-9A-Za-z]{20,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

SAST_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "sql_fstring_injection",
        "HIGH",
        re.compile(r"\.execute\(\s*f[\"']"),
    ),
    (
        "shell_true_subprocess",
        "HIGH",
        re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"),
    ),
    (
        "dynamic_eval_exec",
        "HIGH",
        re.compile(r"\b(?:eval|exec)\s*\("),
    ),
    (
        "unsafe_pickle_loads",
        "HIGH",
        re.compile(r"\bpickle\.loads?\s*\("),
    ),
    (
        "unsafe_yaml_load",
        "MEDIUM",
        re.compile(r"\byaml\.load\s*\((?![^)]*SafeLoader)"),
    ),
]

SCAN_ROOTS = ("campusflow", "factory_app", "scripts", "tests", "docs", "change_requests")
SKIP_NAMES = {".env", ".env.example", "security_scan.py"}


def _iter_text_files(repo_root: Path, roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for top in roots:
        base = repo_root / top
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root)
            if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                continue
            if path.name in SKIP_NAMES:
                continue
            if path.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".json", ".txt"}:
                continue
            files.append(path)
    return files


def scan_secrets(repo_root: Path = ROOT) -> dict[str, Any]:
    """Deterministic regex secret scan across tracked repository areas."""
    findings: list[dict[str, Any]] = []
    for path in _iter_text_files(repo_root, SCAN_ROOTS):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(repo_root).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            for rule_id, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "rule": rule_id,
                            "severity": "HIGH",
                            "file": rel,
                            "line": line_no,
                            "message": f"Potential secret pattern ({rule_id}) detected",
                        }
                    )
    high = len(findings)
    return {
        "tool": "secret_scan",
        "status": "FAIL" if high > 0 else "PASS",
        "high": high,
        "medium": 0,
        "low": 0,
        "findings": findings,
    }


def scan_sast_builtin(repo_root: Path = ROOT) -> dict[str, Any]:
    """Built-in deterministic SAST rules over product code (`campusflow/`)."""
    findings: list[dict[str, Any]] = []
    for path in _iter_text_files(repo_root, ("campusflow",)):
        if path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(repo_root).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            for rule_id, severity, pattern in SAST_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "rule": rule_id,
                            "severity": severity,
                            "file": rel,
                            "line": line_no,
                            "message": f"Static security rule triggered: {rule_id}",
                        }
                    )
    high = sum(1 for f in findings if f["severity"] == "HIGH")
    medium = sum(1 for f in findings if f["severity"] == "MEDIUM")
    return {
        "tool": "sast_builtin",
        "status": "FAIL" if high > 0 else "PASS",
        "high": high,
        "medium": medium,
        "low": 0,
        "findings": findings,
    }


def scan_semgrep(repo_root: Path = ROOT) -> dict[str, Any]:
    """Run Semgrep if installed on PATH; report UNAVAILABLE honestly otherwise."""
    exe = shutil.which("semgrep")
    if not exe:
        return {
            "tool": "semgrep",
            "status": "UNAVAILABLE",
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
            "note": "semgrep CLI not installed in this environment",
        }
    proc = subprocess.run(
        [exe, "--config", "p/python", "--json", "--quiet", "campusflow"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    findings: list[dict[str, Any]] = []
    high = medium = low = 0
    try:
        data = json.loads(proc.stdout or "{}")
        for item in data.get("results", []):
            sev = str(item.get("extra", {}).get("severity", "INFO")).upper()
            mapped = "HIGH" if sev == "ERROR" else ("MEDIUM" if sev == "WARNING" else "LOW")
            if mapped == "HIGH":
                high += 1
            elif mapped == "MEDIUM":
                medium += 1
            else:
                low += 1
            findings.append(
                {
                    "rule": item.get("check_id", "semgrep"),
                    "severity": mapped,
                    "file": str(item.get("path", "")).replace("\\", "/"),
                    "line": int(item.get("start", {}).get("line", 0)),
                    "message": item.get("extra", {}).get("message", ""),
                }
            )
    except json.JSONDecodeError:
        return {
            "tool": "semgrep",
            "status": "FAIL",
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
            "note": proc.stderr.strip()[:500],
        }
    return {
        "tool": "semgrep",
        "status": "FAIL" if high > 0 else "PASS",
        "high": high,
        "medium": medium,
        "low": low,
        "findings": findings,
    }


def scan_pip_audit(repo_root: Path = ROOT) -> dict[str, Any]:
    """Run pip-audit if installed on PATH; report UNAVAILABLE honestly otherwise."""
    exe = shutil.which("pip-audit")
    if not exe:
        return {
            "tool": "pip-audit",
            "status": "UNAVAILABLE",
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
            "note": "pip-audit CLI not installed in this environment",
        }
    proc = subprocess.run(
        [exe, "--format", "json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    findings: list[dict[str, Any]] = []
    try:
        data = json.loads(proc.stdout or "{}")
        for dep in data.get("dependencies", []):
            for vuln in dep.get("vulns", []):
                findings.append(
                    {
                        "rule": vuln.get("id", "CVE"),
                        "severity": "HIGH",
                        "file": "pyproject.toml",
                        "line": 0,
                        "message": f"{dep.get('name')}=={dep.get('version')}: {vuln.get('id')}",
                    }
                )
    except json.JSONDecodeError:
        return {
            "tool": "pip-audit",
            "status": "FAIL",
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
            "note": proc.stderr.strip()[:500],
        }
    high = len(findings)
    return {
        "tool": "pip-audit",
        "status": "FAIL" if high > 0 else "PASS",
        "high": high,
        "medium": 0,
        "low": 0,
        "findings": findings,
    }


def run_all_scans(repo_root: Path = ROOT) -> dict[str, Any]:
    """Run all deterministic security scanners and return a structured report."""
    scanners = [
        scan_secrets(repo_root),
        scan_sast_builtin(repo_root),
        scan_semgrep(repo_root),
        scan_pip_audit(repo_root),
    ]
    total_high = sum(s["high"] for s in scanners)
    total_medium = sum(s["medium"] for s in scanners)
    blocking = any(s["status"] == "FAIL" for s in scanners)
    return {
        "ok": not blocking,
        "high": total_high,
        "medium": total_medium,
        "scanners": scanners,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Security Gate scanners")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)

    result = run_all_scans(ROOT)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for s in result["scanners"]:
            print(
                f"{s['tool']:14s}: {s['status']} "
                f"(high={s['high']}, medium={s['medium']}, low={s['low']})"
            )
            for f in s["findings"]:
                print(f"  - [{f['severity']}] {f['file']}:{f['line']} {f['message']}")
        print(f"SECURITY_SCAN: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
