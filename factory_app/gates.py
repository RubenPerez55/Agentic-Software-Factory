"""Human Gate decision recording and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state import (
    AWAITING_CLARIFICATION,
    AWAITING_FINDING_DECISIONS,
    AWAITING_PLAN_APPROVAL,
    AWAITING_RELEASE_DECISION,
    NOT_READY,
    READY_FOR_HUMAN_MERGE,
    REJECTED,
    REPO_ROOT,
    StateTransitionError,
    load_state,
    normalize_change_id,
    run_dir,
    save_state,
    transition,
    utc_now,
)

GATE_SPECS: dict[str, dict[str, Any]] = {
    "clarification": {
        "expected_state": AWAITING_CLARIFICATION,
        "artifact": "02-human-requirement-decision.md",
        "valid_decisions": {"APPROVED", "REJECTED"},
        "allowed_roles": {"Product Owner"},
    },
    "plan": {
        "expected_state": AWAITING_PLAN_APPROVAL,
        "artifact": "04-human-plan-approval.md",
        "valid_decisions": {"APPROVED", "MODIFIED", "REJECTED"},
        "allowed_roles": {"Product Owner", "Tech Lead", "Product Owner / Tech Lead"},
    },
    "findings": {
        "expected_state": AWAITING_FINDING_DECISIONS,
        "artifact": "10-human-review-decisions.md",
        "valid_decisions": {"APPROVED", "ACCEPTED", "REJECTED", "MODIFIED", "DEFERRED"},
        "allowed_roles": {"Human Reviewer"},
    },
    "release": {
        "expected_state": AWAITING_RELEASE_DECISION,
        "artifact": "15-release-decision.json",
        "valid_decisions": {"READY_FOR_HUMAN_MERGE", "NOT_READY", "APPROVED", "REJECTED"},
        "allowed_roles": {"Release Manager"},
    },
}


def _format_markdown_decision(record: dict[str, Any]) -> str:
    return (
        f"# Human Gate Decision — {record['gate'].title()} ({record['change_id']})\n\n"
        f"- **Decision:** `{record['decision']}`\n"
        f"- **By:** {record['by']}\n"
        f"- **Role:** {record['role']}\n"
        f"- **Recorded at:** {record['recorded_at']}\n"
        f"- **Reason / Notes:** {record['reason']}\n\n"
        "```json\n"
        f"{json.dumps(record, indent=2)}\n"
        "```\n"
    )


def record_gate_decision(
    change_id: str,
    gate: str,
    decision: str,
    reason: str,
    *,
    by: str,
    role: str,
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[str, Any], Path]:
    """Validate and record a signed human decision for a blocking Human Gate."""
    cid = normalize_change_id(change_id)
    gate_key = gate.strip().lower()
    dec = decision.strip().upper()
    clean_reason = reason.strip()
    clean_by = by.strip()
    clean_role = role.strip()

    if gate_key not in GATE_SPECS:
        raise ValueError(f"Invalid gate {gate!r}. Expected one of: {sorted(GATE_SPECS)}")
    spec = GATE_SPECS[gate_key]

    if dec not in spec["valid_decisions"]:
        raise ValueError(
            f"Invalid decision {decision!r} for gate {gate_key!r}. "
            f"Expected one of: {sorted(spec['valid_decisions'])}"
        )
    if not clean_reason:
        raise ValueError("Human decision requires a non-empty reason")
    if not clean_by:
        raise ValueError("Human decision requires --by (person name)")
    if not clean_role:
        raise ValueError("Human decision requires --role (human role)")

    # Enforce who may decide each gate (docs/factory/HUMAN_ROLES.md). Case-insensitive,
    # but the recorded role is normalized to the canonical spelling.
    canonical_roles = {r.lower(): r for r in spec["allowed_roles"]}
    if clean_role.lower() not in canonical_roles:
        raise ValueError(
            f"Role {clean_role!r} is not allowed to decide gate {gate_key!r}. "
            f"Allowed roles: {sorted(spec['allowed_roles'])}"
        )
    clean_role = canonical_roles[clean_role.lower()]

    # Normalize release aliases so state matches STATE_MACHINE.md
    if gate_key == "release":
        if dec == "APPROVED":
            dec = READY_FOR_HUMAN_MERGE
        elif dec == "REJECTED":
            dec = NOT_READY

    state = load_state(cid, repo_root)
    if state["status"] != spec["expected_state"]:
        raise StateTransitionError(
            f"Gate {gate_key!r} cannot be decided while run is in state "
            f"{state['status']!r} (expected {spec['expected_state']!r})"
        )

    record = {
        "change_id": cid,
        "gate": gate_key,
        "decision": dec,
        "by": clean_by,
        "role": clean_role,
        "reason": clean_reason,
        "recorded_at": utc_now(),
    }

    artifact_name = spec["artifact"]
    artifact_path = run_dir(cid, repo_root) / artifact_name
    if artifact_name.endswith(".json"):
        artifact_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    else:
        artifact_path.write_text(_format_markdown_decision(record), encoding="utf-8")

    actor = f"{clean_by} ({clean_role})"
    state["human_gates"][gate_key] = dec

    if gate_key in {"clarification", "plan"} and dec == "REJECTED":
        transition(
            state,
            REJECTED,
            actor=actor,
            artifact=artifact_name,
            note=clean_reason,
            repo_root=repo_root,
        )
    elif gate_key == "release":
        target = READY_FOR_HUMAN_MERGE if dec == READY_FOR_HUMAN_MERGE else NOT_READY
        transition(
            state,
            target,
            actor=actor,
            artifact=artifact_name,
            note=clean_reason,
            repo_root=repo_root,
        )
    else:
        state["history"].append(
            {
                "at": record["recorded_at"],
                "actor": actor,
                "session_id": None,
                "from": state["status"],
                "to": state["status"],
                "artifact": artifact_name,
                "note": f"Gate {gate_key} recorded as {dec}: {clean_reason}",
            }
        )
        save_state(state, repo_root)

    return state, artifact_path
