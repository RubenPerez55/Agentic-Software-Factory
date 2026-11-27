"""Record a signed human decision for a blocking Human Gate.

Usage:
  python scripts/approve_gate.py CR-001 plan APPROVED "Scope and tests reviewed" \\
      --by "Ruben Perez" --role "Tech Lead"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory_app.gates import GATE_SPECS, record_gate_decision  # noqa: E402
from factory_app.state import StateTransitionError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a Human Gate decision")
    parser.add_argument("change_id", help="Change Request ID, e.g. CR-001")
    parser.add_argument("gate", choices=sorted(GATE_SPECS), help="Human gate name")
    parser.add_argument("decision", help="Decision (e.g. APPROVED, MODIFIED, REJECTED)")
    parser.add_argument("reason", help="Explicit justification for the decision")
    parser.add_argument("--by", required=True, help="Full name of the human decision maker")
    parser.add_argument(
        "--role",
        required=True,
        help="Human role allowed for the gate: Product Owner, Tech Lead, Human Reviewer, "
        "Release Manager",
    )
    args = parser.parse_args(argv)

    try:
        state, artifact_path = record_gate_decision(
            args.change_id,
            args.gate,
            args.decision,
            args.reason,
            by=args.by,
            role=args.role,
            repo_root=ROOT,
        )
    except (ValueError, FileNotFoundError, StateTransitionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    rel = artifact_path.relative_to(ROOT)
    print(f"Recorded {args.gate}: {args.decision.upper()} -> {rel} (status={state['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
