"""Initialize a new factory run under runs/<CR-ID>/ using factory_app.state."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory_app.state import init_run, run_dir  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/start_run.py CR-001")
    change_id = sys.argv[1].strip().upper()
    try:
        init_run(change_id, repo_root=ROOT, exist_ok=False)
    except (FileExistsError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Created {run_dir(change_id, ROOT).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
