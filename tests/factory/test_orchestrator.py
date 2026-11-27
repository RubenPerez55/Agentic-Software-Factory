"""Deterministic tests for state machine, Human Gates, and orchestrator (0 LLM calls)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from factory_app import tools
from factory_app.gates import record_gate_decision
from factory_app.orchestrator import FactoryOrchestrator, HumanGateBlockedError, extract_json_block
from factory_app.state import (
    AWAITING_CLARIFICATION,
    AWAITING_PLAN_APPROVAL,
    BLOCKED,
    CODING_RUNNING,
    CONSOLIDATING_EVIDENCE,
    CREATED,
    PLANNING_RUNNING,
    READY_FOR_HUMAN_MERGE,
    REJECTED,
    REVIEWING,
    StateTransitionError,
    init_run,
    load_state,
    transition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_workspace(tmp_path: Path) -> Path:
    """Create a minimal repo copy with docs and change_requests for isolated tests."""
    for folder in ("docs", "change_requests"):
        shutil.copytree(REPO_ROOT / folder, tmp_path / folder)
    (tmp_path / "runs").mkdir()
    return tmp_path


def _intake_md(recommendation: str) -> str:
    payload = {
        "requested_outcome": "Test outcome",
        "affected_requirements": ["FR-03"],
        "acceptance_criteria": ["AC-CR001.1"],
        "likely_areas": ["campusflow/service.py"],
        "ambiguities": [],
        "conflicts": [],
        "context_used": ["docs/REPO_MAP.md"],
        "recommendation": recommendation,
    }
    return f"# Intake Report\n\n```json\n{json.dumps(payload, indent=2)}\n```\n"


def _planner_md() -> str:
    payload = {
        "scope": {"in": ["Waitlist"], "out": ["Auth"]},
        "tasks": [
            {
                "id": "TASK-1",
                "description": "Add waitlist",
                "files": ["campusflow/service.py"],
                "covers": ["AC-CR001.2"],
            }
        ],
        "tests_to_add_or_change": [],
        "existing_tests_in_conflict": [
            {
                "test": "test_registration_rejects_when_event_is_full",
                "proposal": "Update for WAITLISTED with Tech Lead approval",
            }
        ],
        "architecture_constraints": ["API -> Service -> Repository"],
        "security_considerations": [],
        "verification_commands": ["uv run python scripts/verify_repo.py"],
        "assumptions": [],
        "open_questions": [],
        "context_used": ["docs/REQUIREMENTS.md"],
    }
    return f"# Implementation Plan\n\n```json\n{json.dumps(payload, indent=2)}\n```\n"


def test_extract_json_block():
    parsed = extract_json_block(_intake_md("PROCEED"))
    assert parsed is not None
    assert parsed["recommendation"] == "PROCEED"
    assert extract_json_block("No JSON here") is None


def test_state_machine_enforces_guards(tmp_path: Path):
    ws = _make_workspace(tmp_path)
    state = init_run("CR-001", repo_root=ws)
    assert state["status"] == CREATED

    with pytest.raises(StateTransitionError):
        transition(state, CODING_RUNNING, actor="Test", repo_root=ws)

    # Force to AWAITING_PLAN_APPROVAL without plan approval: guard must block CODING_RUNNING.
    state["status"] = AWAITING_PLAN_APPROVAL
    with pytest.raises(StateTransitionError, match="plan must be APPROVED"):
        transition(state, CODING_RUNNING, actor="Test", repo_root=ws)

    # Verification guard blocks REVIEWING unless PASS.
    state["status"] = "VERIFYING"
    with pytest.raises(StateTransitionError, match="verification.status must be PASS"):
        transition(state, REVIEWING, actor="Test", repo_root=ws)

    # Findings guard blocks CONSOLIDATING_EVIDENCE without human decisions.
    state["status"] = "AWAITING_FINDING_DECISIONS"
    with pytest.raises(StateTransitionError, match="human decisions"):
        transition(state, CONSOLIDATING_EVIDENCE, actor="Test", repo_root=ws)

    # Terminal state has no automatic merge transition.
    state["status"] = READY_FOR_HUMAN_MERGE
    with pytest.raises(StateTransitionError):
        transition(state, "MERGED", actor="Test", repo_root=ws)


def _make_fake_verifier(results: list[bool]):
    idx = {"n": 0}

    def _verify(change_id: str, repo_root: Path, iteration: int) -> tuple[bool, str, str]:
        passed = results[min(idx["n"], len(results) - 1)]
        idx["n"] += 1
        artifact = (
            "07-verification.txt" if iteration == 1 else f"07-verification.iter{iteration}.txt"
        )
        text = f"VERIFY_REPO: {'PASS' if passed else 'FAIL'} (iter {iteration})\n"
        (repo_root / "runs" / change_id / artifact).write_text(text, encoding="utf-8")
        return passed, text, artifact

    return _verify


def test_cr001_stops_at_gate1_blocks_until_approved(tmp_path: Path):
    ws = _make_workspace(tmp_path)
    calls: list[tuple[str, str]] = []

    def fake_runner(agent, prompt_text, session_id, initial_state):
        calls.append((agent.name, session_id))
        if agent.name == "IntakeAgent":
            return _intake_md("PROCEED")
        if agent.name == "PlannerAgent":
            return _planner_md()
        return f"# {agent.name} report\n"

    orch = FactoryOrchestrator(
        repo_root=ws,
        agent_runner=fake_runner,
        verification_runner=_make_fake_verifier([True]),
    )
    state = orch.run("CR-001")

    assert state["status"] == AWAITING_PLAN_APPROVAL
    assert [name for name, _ in calls] == ["IntakeAgent", "PlannerAgent"]
    assert calls[0][1] != calls[1][1]  # Distinct ADK session IDs
    assert (ws / "runs/CR-001/01-intake-report.md").is_file()
    assert (ws / "runs/CR-001/03-implementation-plan.md").is_file()

    # Resuming without Gate 1 approval MUST fail.
    with pytest.raises(HumanGateBlockedError):
        orch.resume("CR-001")

    # Recording MODIFIED re-runs Planner with approval notes.
    record_gate_decision(
        "CR-001",
        "plan",
        "MODIFIED",
        "Add FIFO boundary test",
        by="Ruben Perez",
        role="Tech Lead",
        repo_root=ws,
    )
    assert (ws / "runs/CR-001/04-human-plan-approval.md").is_file()
    state = orch.resume("CR-001")
    assert state["status"] == AWAITING_PLAN_APPROVAL
    assert [name for name, _ in calls] == ["IntakeAgent", "PlannerAgent", "PlannerAgent"]

    # Recording APPROVED runs M2: Coder -> Test Analyst -> Verification PASS -> REVIEWING.
    record_gate_decision(
        "CR-001",
        "plan",
        "APPROVED",
        "Plan and conflict resolution approved",
        by="Ruben Perez",
        role="Tech Lead",
        repo_root=ws,
    )
    state = orch.resume("CR-001")
    assert state["status"] == REVIEWING
    assert state["verification"]["status"] == "PASS"
    assert [name for name, _ in calls] == [
        "IntakeAgent",
        "PlannerAgent",
        "PlannerAgent",
        "CoderAgent",
        "TestAnalystAgent",
    ]
    assert len({sid for _, sid in calls}) == 5  # Every invocation gets an isolated session
    assert (ws / "runs/CR-001/05-coder-report.md").is_file()
    assert (ws / "runs/CR-001/06-test-analysis.md").is_file()
    assert (ws / "runs/CR-001/07-verification.txt").is_file()


def test_m2_verification_fail_loops_to_coder_and_recovers(tmp_path: Path):
    ws = _make_workspace(tmp_path)
    coder_prompts: list[str] = []

    def fake_runner(agent, prompt_text, session_id, initial_state):
        if agent.name == "IntakeAgent":
            return _intake_md("PROCEED")
        if agent.name == "PlannerAgent":
            return _planner_md()
        if agent.name == "CoderAgent":
            coder_prompts.append(prompt_text)
        return f"# {agent.name} report\n"

    orch = FactoryOrchestrator(
        repo_root=ws,
        agent_runner=fake_runner,
        verification_runner=_make_fake_verifier([False, True]),
        max_verify_iterations=3,
    )
    orch.run("CR-001")
    record_gate_decision(
        "CR-001", "plan", "APPROVED", "Go", by="Ruben Perez", role="Tech Lead", repo_root=ws
    )
    state = orch.resume("CR-001")

    assert state["status"] == REVIEWING
    assert state["iterations"]["verify"] == 2
    assert len(coder_prompts) == 2
    assert "07-verification.txt" in coder_prompts[1]
    assert (ws / "runs/CR-001/07-verification.txt").is_file()
    assert (ws / "runs/CR-001/07-verification.iter2.txt").is_file()


def test_m2_verification_exhausts_iterations_and_blocks(tmp_path: Path):
    ws = _make_workspace(tmp_path)

    def fake_runner(agent, prompt_text, session_id, initial_state):
        if agent.name == "IntakeAgent":
            return _intake_md("PROCEED")
        if agent.name == "PlannerAgent":
            return _planner_md()
        return f"# {agent.name} report\n"

    orch = FactoryOrchestrator(
        repo_root=ws,
        agent_runner=fake_runner,
        verification_runner=_make_fake_verifier([False, False]),
        max_verify_iterations=2,
    )
    orch.run("CR-001")
    record_gate_decision(
        "CR-001", "plan", "APPROVED", "Go", by="Ruben Perez", role="Tech Lead", repo_root=ws
    )
    state = orch.resume("CR-001")

    assert state["status"] == BLOCKED
    assert state["iterations"]["verify"] == 2
    assert state["verification"]["status"] == "FAIL"


def test_m2_coder_is_plan_scoped_during_execution(monkeypatch, tmp_path: Path):
    ws = _make_workspace(tmp_path)
    monkeypatch.setattr(tools, "REPO_ROOT", ws)
    write_results: dict[str, bool] = {}

    def fake_runner(agent, prompt_text, session_id, initial_state):
        if agent.name == "IntakeAgent":
            return _intake_md("PROCEED")
        if agent.name == "PlannerAgent":
            return _planner_md()  # Only authorizes campusflow/service.py
        if agent.name == "CoderAgent":
            write_results["in_plan"] = tools.write_coder_file("campusflow/service.py", "x = 1\n")[
                "ok"
            ]
            write_results["out_of_plan"] = tools.write_coder_file("campusflow/api.py", "y = 2\n")[
                "ok"
            ]
        return f"# {agent.name} report\n"

    orch = FactoryOrchestrator(
        repo_root=ws,
        agent_runner=fake_runner,
        verification_runner=_make_fake_verifier([True]),
    )
    orch.run("CR-001")
    record_gate_decision(
        "CR-001", "plan", "APPROVED", "Go", by="Ruben Perez", role="Tech Lead", repo_root=ws
    )
    state = orch.resume("CR-001")

    assert state["status"] == REVIEWING
    assert write_results == {"in_plan": True, "out_of_plan": False}


def test_cr005_stops_at_clarification_then_resumes_after_po_decision(tmp_path: Path):
    ws = _make_workspace(tmp_path)
    seen_prompts: list[tuple[str, str]] = []

    def fake_runner(agent, prompt_text, session_id, initial_state):
        seen_prompts.append((agent.name, prompt_text))
        if agent.name == "IntakeAgent":
            if "02-human-requirement-decision.md" in prompt_text:
                return _intake_md("PROCEED")
            return _intake_md("HUMAN_CLARIFICATION_REQUIRED")
        return _planner_md()

    orch = FactoryOrchestrator(repo_root=ws, agent_runner=fake_runner)
    state = orch.run("CR-005")

    assert state["status"] == AWAITING_CLARIFICATION
    assert [name for name, _ in seen_prompts] == ["IntakeAgent"]  # Planner did NOT run

    with pytest.raises(HumanGateBlockedError):
        orch.resume("CR-005")

    record_gate_decision(
        "CR-005",
        "clarification",
        "APPROVED",
        "STAFF has priority inside waitlist only, FIFO per group.",
        by="Ruben Perez",
        role="Product Owner",
        repo_root=ws,
    )
    assert (ws / "runs/CR-005/02-human-requirement-decision.md").is_file()

    state = orch.resume("CR-005")
    assert state["status"] == AWAITING_PLAN_APPROVAL
    assert [name for name, _ in seen_prompts] == ["IntakeAgent", "IntakeAgent", "PlannerAgent"]


def test_rate_limit_retry_and_checkpoint_resume(tmp_path: Path):
    ws = _make_workspace(tmp_path)
    slept: list[float] = []
    attempts = {"planner": 0}

    def flaky_runner(agent, prompt_text, session_id, initial_state):
        if agent.name == "IntakeAgent":
            return _intake_md("PROCEED")
        attempts["planner"] += 1
        if attempts["planner"] <= 2:
            raise RuntimeError("429 RESOURCE_EXHAUSTED: Free Tier rate limit")
        return _planner_md()

    # First run exhausts max_retries=1 on Planner, leaving checkpoint at PLANNING_RUNNING.
    orch_fail = FactoryOrchestrator(
        repo_root=ws,
        agent_runner=flaky_runner,
        max_retries=1,
        base_backoff_seconds=1.0,
        sleep_fn=slept.append,
    )
    with pytest.raises(RuntimeError, match="429"):
        orch_fail.run("CR-001")

    saved = load_state("CR-001", repo_root=ws)
    assert saved["status"] == PLANNING_RUNNING
    assert saved["rate_limit_retries"] == 1
    assert slept == [1.0]

    # Resume continues directly from Planner without re-running Intake.
    state = orch_fail.resume("CR-001")
    assert state["status"] == AWAITING_PLAN_APPROVAL


def test_gate_validation_rejects_missing_metadata_or_wrong_state(tmp_path: Path):
    ws = _make_workspace(tmp_path)
    init_run("CR-001", repo_root=ws)

    with pytest.raises(ValueError, match="reason"):
        record_gate_decision(
            "CR-001", "plan", "APPROVED", "   ", by="Hector", role="Tech Lead", repo_root=ws
        )

    with pytest.raises(StateTransitionError, match="cannot be decided"):
        record_gate_decision(
            "CR-001", "plan", "APPROVED", "ok", by="Hector", role="Tech Lead", repo_root=ws
        )

    # Only the roles in HUMAN_ROLES.md may decide a gate (no agent or wrong human role).
    for bad_role in ("Coder", "CoderAgent", "Release Manager"):
        with pytest.raises(ValueError, match="not allowed to decide gate 'plan'"):
            record_gate_decision(
                "CR-001", "plan", "APPROVED", "ok", by="Hector", role=bad_role, repo_root=ws
            )
    with pytest.raises(ValueError, match="not allowed to decide gate 'release'"):
        record_gate_decision(
            "CR-001", "release", "APPROVED", "ok", by="Hector", role="Tech Lead", repo_root=ws
        )

    # Rejection transitions to REJECTED terminal state.
    orch = FactoryOrchestrator(
        repo_root=ws,
        agent_runner=lambda agent, *_: _intake_md("HUMAN_CLARIFICATION_REQUIRED"),
    )
    orch.run("CR-001")
    state, _ = record_gate_decision(
        "CR-001",
        "clarification",
        "REJECTED",
        "Out of scope",
        by="Ruben Perez",
        role="Product Owner",
        repo_root=ws,
    )
    assert state["status"] == REJECTED


def test_gate_role_is_case_insensitive_and_recorded_canonically(tmp_path: Path):
    ws = _make_workspace(tmp_path)
    orch = FactoryOrchestrator(
        repo_root=ws,
        agent_runner=lambda agent, *_: _intake_md("HUMAN_CLARIFICATION_REQUIRED"),
    )
    orch.run("CR-005")
    state, artifact = record_gate_decision(
        "CR-005",
        "clarification",
        "REJECTED",
        "Out of scope",
        by="Ruben Perez",
        role="product owner",
        repo_root=ws,
    )
    assert state["status"] == REJECTED
    assert "**Role:** Product Owner" in artifact.read_text(encoding="utf-8")
