"""Explicit state machine and checkpoint persistence for factory runs."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Formal states from docs/factory/STATE_MACHINE.md
CREATED = "CREATED"
INTAKE_RUNNING = "INTAKE_RUNNING"
AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
PLANNING_RUNNING = "PLANNING_RUNNING"
AWAITING_PLAN_APPROVAL = "AWAITING_PLAN_APPROVAL"
CODING_RUNNING = "CODING_RUNNING"
TEST_ANALYSIS_RUNNING = "TEST_ANALYSIS_RUNNING"
VERIFYING = "VERIFYING"
REVIEWING = "REVIEWING"
AWAITING_FINDING_DECISIONS = "AWAITING_FINDING_DECISIONS"
FIXING = "FIXING"
REVERIFYING = "REVERIFYING"
REREVIEWING = "REREVIEWING"
CONSOLIDATING_EVIDENCE = "CONSOLIDATING_EVIDENCE"
AWAITING_RELEASE_DECISION = "AWAITING_RELEASE_DECISION"
READY_FOR_HUMAN_MERGE = "READY_FOR_HUMAN_MERGE"
NOT_READY = "NOT_READY"
REJECTED = "REJECTED"
BLOCKED = "BLOCKED"

HUMAN_WAIT_STATES = {
    AWAITING_CLARIFICATION,
    AWAITING_PLAN_APPROVAL,
    AWAITING_FINDING_DECISIONS,
    AWAITING_RELEASE_DECISION,
}

TERMINAL_STATES = {
    READY_FOR_HUMAN_MERGE,
    NOT_READY,
    REJECTED,
    BLOCKED,
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    CREATED: {INTAKE_RUNNING},
    INTAKE_RUNNING: {AWAITING_CLARIFICATION, PLANNING_RUNNING, BLOCKED},
    AWAITING_CLARIFICATION: {INTAKE_RUNNING, REJECTED},
    PLANNING_RUNNING: {AWAITING_PLAN_APPROVAL, AWAITING_CLARIFICATION, BLOCKED},
    AWAITING_PLAN_APPROVAL: {CODING_RUNNING, PLANNING_RUNNING, REJECTED},
    CODING_RUNNING: {TEST_ANALYSIS_RUNNING, BLOCKED},
    TEST_ANALYSIS_RUNNING: {VERIFYING, BLOCKED},
    VERIFYING: {REVIEWING, CODING_RUNNING, BLOCKED},
    REVIEWING: {AWAITING_FINDING_DECISIONS, BLOCKED},
    AWAITING_FINDING_DECISIONS: {FIXING, CONSOLIDATING_EVIDENCE},
    FIXING: {REVERIFYING, BLOCKED},
    REVERIFYING: {REREVIEWING, FIXING, BLOCKED},
    REREVIEWING: {AWAITING_FINDING_DECISIONS, BLOCKED},
    CONSOLIDATING_EVIDENCE: {AWAITING_RELEASE_DECISION, BLOCKED},
    AWAITING_RELEASE_DECISION: {READY_FOR_HUMAN_MERGE, NOT_READY},
    READY_FOR_HUMAN_MERGE: set(),
    NOT_READY: set(),
    REJECTED: set(),
    BLOCKED: set(),
}


class StateTransitionError(ValueError):
    """Raised when a transition violates the factory state machine or gate guards."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_change_id(change_id: str) -> str:
    return change_id.strip().upper()


def find_change_request(change_id: str, repo_root: Path = REPO_ROOT) -> Path:
    cid = normalize_change_id(change_id)
    matches = sorted((repo_root / "change_requests").glob(f"{cid}-*.md"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one Change Request for {cid}; found {len(matches)}"
        )
    return matches[0]


def run_dir(change_id: str, repo_root: Path = REPO_ROOT) -> Path:
    return repo_root / "runs" / normalize_change_id(change_id)


def state_path(change_id: str, repo_root: Path = REPO_ROOT) -> Path:
    return run_dir(change_id, repo_root) / "factory-state.json"


def init_run(
    change_id: str,
    repo_root: Path = REPO_ROOT,
    exist_ok: bool = False,
) -> dict[str, Any]:
    """Create runs/<CR-ID>/, copy 00-change-request.md, and write initial state."""
    cid = normalize_change_id(change_id)
    folder = run_dir(cid, repo_root)
    s_path = state_path(cid, repo_root)

    if s_path.exists():
        if exist_ok:
            return load_state(cid, repo_root)
        raise FileExistsError(f"Run already exists: {folder}")

    source_cr = find_change_request(cid, repo_root)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_cr, folder / "00-change-request.md")

    now = utc_now()
    state: dict[str, Any] = {
        "change_id": cid,
        "status": CREATED,
        "branch": f"cr/{cid}",
        "created_at": now,
        "updated_at": now,
        "iterations": {"verify": 0, "review": 0},
        "rate_limit_retries": 0,
        "human_gates": {
            "clarification": "NOT_REQUIRED",
            "plan": "PENDING",
            "findings": "PENDING",
            "release": "PENDING",
        },
        "verification": {"status": "NOT_RUN"},
        "review": {"status": "NOT_RUN", "must_fix": 0, "should_fix": 0},
        "security": {"status": "NOT_RUN", "high": 0, "medium": 0},
        "history": [
            {
                "at": now,
                "actor": "Orchestrator",
                "session_id": None,
                "from": None,
                "to": CREATED,
                "artifact": "00-change-request.md",
                "note": f"Initialized from {source_cr.name}",
            }
        ],
    }
    save_state(state, repo_root)
    return state


def load_state(change_id: str, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    s_path = state_path(change_id, repo_root)
    if not s_path.exists():
        raise FileNotFoundError(f"Run not found: {normalize_change_id(change_id)}")
    return json.loads(s_path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any], repo_root: Path = REPO_ROOT) -> Path:
    state["updated_at"] = utc_now()
    s_path = state_path(state["change_id"], repo_root)
    s_path.parent.mkdir(parents=True, exist_ok=True)
    s_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return s_path


def transition(
    state: dict[str, Any],
    to_state: str,
    *,
    actor: str,
    artifact: str | None = None,
    session_id: str | None = None,
    note: str = "",
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Validate state transition + gate guards, append history, and persist checkpoint."""
    current = state["status"]
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if to_state not in allowed:
        raise StateTransitionError(
            f"Illegal transition {current} -> {to_state} (allowed: {sorted(allowed)})"
        )

    # Guard rules from docs/factory/STATE_MACHINE.md
    if to_state == CODING_RUNNING and state["human_gates"].get("plan") != "APPROVED":
        raise StateTransitionError(
            "Cannot enter CODING_RUNNING: human_gates.plan must be APPROVED"
        )
    if to_state == REVIEWING and state["verification"].get("status") != "PASS":
        raise StateTransitionError(
            "Cannot enter REVIEWING: verification.status must be PASS"
        )
    if to_state == CONSOLIDATING_EVIDENCE and state["human_gates"].get("findings") not in {
        "APPROVED",
        "NO_BLOCKING",
    }:
        raise StateTransitionError(
            "Cannot enter CONSOLIDATING_EVIDENCE: findings must have human decisions"
        )

    state["status"] = to_state
    state["history"].append(
        {
            "at": utc_now(),
            "actor": actor,
            "session_id": session_id,
            "from": current,
            "to": to_state,
            "artifact": artifact,
            "note": note,
        }
    )
    save_state(state, repo_root)
    return state
