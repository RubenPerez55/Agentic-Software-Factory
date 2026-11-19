"""Verification Gate: deterministic checks that block the factory on FAIL.

Checks:
  tests      pytest
  lint       ruff
  contracts  agent YAML contracts vs. ADK wiring (factory_app/contract_checks.py)

Usage:
  python scripts/verify_repo.py                    # print results, exit 1 on FAIL
  python scripts/verify_repo.py --change CR-001    # also save runs/CR-001/07-verification.txt
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COMMANDS = {
    "tests": [sys.executable, "-m", "pytest", "-q"],
    "lint": [
        sys.executable, "-m", "ruff", "check", "campusflow", "tests", "factory_app", "scripts"
    ],
}
CHANGE_ID = re.compile(r"^CR-\d{3}$")


def run_command(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        command, cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8"
    )
    output = f"$ {' '.join(command)}\n{result.stdout}{result.stderr}"
    return result.returncode == 0, output


def run_contracts() -> tuple[bool, str]:
    from factory_app.contract_checks import check_contracts

    errors = check_contracts()
    lines = ["$ contract_checks.check_contracts()"]
    lines += [f"ERROR {e}" for e in errors] or ["all agent contracts OK"]
    return not errors, "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--change", help="CR id (e.g. CR-001) to save evidence under runs/<CR>/")
    args = parser.parse_args(argv)
    if args.change and not CHANGE_ID.match(args.change):
        parser.error("--change must look like CR-001")

    results: dict[str, bool] = {}
    report: list[str] = []
    for name, command in COMMANDS.items():
        ok, output = run_command(command)
        results[name] = ok
        report.append(f"## {name}\n{output}")
    ok, output = run_contracts()
    results["contracts"] = ok
    report.append(f"## contracts\n{output}")

    passed = all(results.values())
    summary = ["## summary"]
    summary += [f"{name}: {'PASS' if ok else 'FAIL'}" for name, ok in results.items()]
    summary.append(f"VERIFY_REPO: {'PASS' if passed else 'FAIL'}")
    text = "\n".join(report) + "\n" + "\n".join(summary) + "\n"
    print(text)

    if args.change:
        out = ROOT / "runs" / args.change / "07-verification.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        out.write_text(f"# Verification {args.change} — {stamp}\n\n{text}", encoding="utf-8")
        print(f"Evidence written to {out.relative_to(ROOT)}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
