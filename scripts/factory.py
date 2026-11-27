"""CLI entrypoint for running, resuming, and inspecting Agentic Software Factory runs.

Usage:
  uv run python scripts/factory.py run CR-001
  uv run python scripts/factory.py resume CR-001
  uv run python scripts/factory.py status CR-001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory_app.orchestrator import FactoryOrchestrator, HumanGateBlockedError  # noqa: E402
from factory_app.state import (  # noqa: E402
    AWAITING_CLARIFICATION,
    AWAITING_FINDING_DECISIONS,
    AWAITING_PLAN_APPROVAL,
    BLOCKED,
    CODING_RUNNING,
    REVIEWING,
    load_state,
    normalize_change_id,
    run_dir,
)


def _next_action_hint(state: dict) -> str:
    cid = state["change_id"]
    status = state["status"]
    if status == AWAITING_CLARIFICATION:
        if state["human_gates"].get("clarification") == "APPROVED":
            return f"Run `uv run python scripts/factory.py resume {cid}` to re-run Intake."
        return (
            f'Product Owner must clarify: `uv run python scripts/approve_gate.py {cid} '
            'clarification APPROVED "<clarification>" --by "<name>" --role "Product Owner"`'
        )
    if status == AWAITING_PLAN_APPROVAL:
        if state["human_gates"].get("plan") in {"APPROVED", "MODIFIED"}:
            return f"Run `uv run python scripts/factory.py resume {cid}`."
        return (
            f'PO / Tech Lead must decide: `uv run python scripts/approve_gate.py {cid} '
            'plan APPROVED "<reason>" --by "<name>" --role "Tech Lead"`'
        )
    if status == CODING_RUNNING:
        return (
            f"Run `uv run python scripts/factory.py resume {cid}` "
            "to continue Coder/Verification."
        )
    if status == REVIEWING:
        return f"Run `uv run python scripts/factory.py resume {cid}` to run Reviewer + Security."
    if status == AWAITING_FINDING_DECISIONS:
        return (
            f'Human Reviewer must decide findings: `uv run python scripts/approve_gate.py {cid} '
            'findings APPROVED "<reason>" --by "<name>" --role "Human Reviewer"`'
        )
    if status == BLOCKED:
        return "Run BLOCKED (verification iterations exhausted). Human intervention required."
    return f"Current state: {status}"


def _print_summary(state: dict) -> None:
    cid = state["change_id"]
    folder = run_dir(cid, ROOT)
    artifacts = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.exists() else []
    print(f"Change ID : {cid}")
    print(f"Status    : {state['status']}")
    print(f"Branch    : {state['branch']}")
    print(f"Retries   : {state.get('rate_limit_retries', 0)}")
    print(f"Gates     : {json.dumps(state['human_gates'])}")
    print(f"Artifacts : {', '.join(artifacts)}")
    print(f"Next step : {_next_action_hint(state)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agentic Software Factory CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd in ("run", "resume"):
        p = sub.add_parser(cmd, help=f"{cmd.title()} a Change Request through the factory")
        p.add_argument("change_id", help="Change Request ID, e.g. CR-001")
        p.add_argument(
            "--model",
            default=None,
            help="Optional Gemini model override (defaults to agents.GEMINI_MODEL)",
        )

    p_status = sub.add_parser("status", help="Show current state and artifacts of a run")
    p_status.add_argument("change_id", help="Change Request ID, e.g. CR-001")
    p_status.add_argument("--json", action="store_true", help="Print raw factory-state.json")

    args = parser.parse_args(argv)
    cid = normalize_change_id(args.change_id)

    if args.command == "status":
        state = load_state(cid, ROOT)
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            _print_summary(state)
        return 0

    orchestrator = FactoryOrchestrator(repo_root=ROOT, model_override=args.model)
    try:
        state = orchestrator.run(cid) if args.command == "run" else orchestrator.resume(cid)
    except HumanGateBlockedError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    _print_summary(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
