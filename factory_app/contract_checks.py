"""Deterministic contract checks for the factory agents (no LLM calls).

Used by the Verification Gate (`scripts/verify_repo.py`) and by
`tests/factory/test_contracts.py`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from factory_app import agents

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "factory_app" / "contracts"

REQUIRED_CONTRACT_KEYS = {
    "agent",
    "role",
    "goal",
    "model",
    "context",
    "allow",
    "deny",
    "output",
    "stop_conditions",
    "human_escalation",
}

EXPECTED_AGENTS = {
    "intake",
    "planner",
    "coder",
    "test_analyst",
    "reviewer",
    "security",
    "evidence",
}

IMPLEMENTED_TOOLS = {
    "list_repo_files",
    "read_repo_file",
    "search_repo",
    "write_run_evidence",
}

READONLY_AGENTS = ("intake", "planner", "reviewer")
WRITE_TOOLS = {"write_run_evidence", "run_baseline_verification"}


def agent_map() -> dict:
    return {
        "intake": agents.intake_agent,
        "planner": agents.planner_agent,
        "coder": agents.coder_agent,
        "test_analyst": agents.test_analyst_agent,
        "reviewer": agents.reviewer_agent,
        "security": agents.security_agent,
        "evidence": agents.evidence_agent,
    }


def allow_names(contract: dict) -> set[str]:
    names: set[str] = set()
    for entry in contract["allow"]:
        if isinstance(entry, str):
            names.add(entry)
        elif isinstance(entry, dict):
            names.update(entry.keys())
    return names


def load_contract(name: str) -> dict:
    return yaml.safe_load((CONTRACTS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))


def check_contracts() -> list[str]:
    """Return a list of human-readable errors; empty means PASS."""
    errors: list[str] = []
    found = {p.stem for p in CONTRACTS_DIR.glob("*.yaml")}
    for name in sorted(EXPECTED_AGENTS - found):
        errors.append(f"{name}.yaml: contract file missing")

    adk_agents = agent_map()
    for name in sorted(EXPECTED_AGENTS & found):
        try:
            data = load_contract(name)
        except yaml.YAMLError as exc:
            errors.append(f"{name}.yaml: invalid YAML ({exc})")
            continue
        if not isinstance(data, dict):
            errors.append(f"{name}.yaml: contract must be a mapping")
            continue

        missing = REQUIRED_CONTRACT_KEYS - set(data.keys())
        if missing:
            errors.append(f"{name}.yaml: missing keys {sorted(missing)}")
            continue
        if data["agent"] != name:
            errors.append(f"{name}.yaml: agent={data['agent']!r} does not match file name")
        if data["model"] != agents.GEMINI_MODEL:
            errors.append(
                f"{name}.yaml: model={data['model']!r} differs from {agents.GEMINI_MODEL!r}"
            )

        allowed = allow_names(data)
        actual_tools = {tool.__name__ for tool in adk_agents[name].tools}
        unexpected = (actual_tools & IMPLEMENTED_TOOLS) - allowed
        if unexpected:
            errors.append(f"{name}: tools not in contract allow list {sorted(unexpected)}")
        missing_tools = (allowed & IMPLEMENTED_TOOLS) - actual_tools
        if missing_tools:
            errors.append(f"{name}: missing implemented contract tools {sorted(missing_tools)}")
        if name in READONLY_AGENTS and actual_tools & WRITE_TOOLS:
            errors.append(
                f"{name}: read-only agent has write tools {sorted(actual_tools & WRITE_TOOLS)}"
            )

    return errors
