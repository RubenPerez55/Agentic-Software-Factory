"""Deterministic Python orchestrator for the Agentic Software Factory (ADR-001).

Controls state transitions, runs each ADK agent in an isolated session,
persists checkpoints after each step, retries transient 429/503 API errors,
and enforces blocking Human Gates.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import agents, tools
from .state import (
    AWAITING_CLARIFICATION,
    AWAITING_FINDING_DECISIONS,
    AWAITING_PLAN_APPROVAL,
    BLOCKED,
    CODING_RUNNING,
    CREATED,
    INTAKE_RUNNING,
    PLANNING_RUNNING,
    REPO_ROOT,
    REVIEWING,
    TERMINAL_STATES,
    TEST_ANALYSIS_RUNNING,
    VERIFYING,
    init_run,
    load_state,
    normalize_change_id,
    run_dir,
    save_state,
    transition,
    utc_now,
)

JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
TRANSIENT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")

AgentRunner = Callable[[Any, str, str, dict[str, Any] | None], str]
VerificationRunner = Callable[[str, Path, int], tuple[bool, str, str]]
SecurityRunner = Callable[[Path], dict[str, Any]]


class HumanGateBlockedError(RuntimeError):
    """Raised when resume() is called while a required Human Gate is still pending."""


def extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract the last fenced ```json``` object from an agent's Markdown response."""
    matches = JSON_FENCE_RE.findall(text)
    for raw in reversed(matches):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _is_transient_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(marker in text for marker in TRANSIENT_MARKERS)


def _read_if_exists(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _build_intake_prompt(change_id: str, repo_root: Path) -> str:
    folder = run_dir(change_id, repo_root)
    sections = [
        f"Process Change Request `{change_id}`.",
        "The mandatory baseline documents are pre-loaded below to minimize API round-trips. "
        "Use `search_repo` / `read_repo_file` only if you need to inspect specific code or tests.",
    ]
    preloaded = [
        ("docs/REPO_MAP.md", repo_root / "docs/REPO_MAP.md"),
        (f"runs/{change_id}/00-change-request.md", folder / "00-change-request.md"),
        ("docs/REQUIREMENTS.md", repo_root / "docs/REQUIREMENTS.md"),
        ("docs/SPEC.md", repo_root / "docs/SPEC.md"),
        ("docs/ARCHITECTURE.md", repo_root / "docs/ARCHITECTURE.md"),
    ]
    clarification = _read_if_exists(folder / "02-human-requirement-decision.md")
    if clarification is not None:
        preloaded.append(
            (
                f"runs/{change_id}/02-human-requirement-decision.md",
                folder / "02-human-requirement-decision.md",
            )
        )

    for label, path in preloaded:
        content = _read_if_exists(path)
        if content is not None:
            sections.append(f"### File: `{label}`\n```markdown\n{content.strip()}\n```")
    return "\n\n".join(sections)


def _build_planner_prompt(change_id: str, repo_root: Path) -> str:
    folder = run_dir(change_id, repo_root)
    sections = [
        f"Create the implementation plan for `{change_id}`.",
        "Use `search_repo` and `read_repo_file` selectively on affected `campusflow/` and "
        "`tests/` files before finalizing your plan.",
    ]
    preloaded = [
        (f"runs/{change_id}/00-change-request.md", folder / "00-change-request.md"),
        ("docs/REQUIREMENTS.md", repo_root / "docs/REQUIREMENTS.md"),
        ("docs/SPEC.md", repo_root / "docs/SPEC.md"),
        ("docs/ARCHITECTURE.md", repo_root / "docs/ARCHITECTURE.md"),
    ]
    for extra in ("02-human-requirement-decision.md", "04-human-plan-approval.md"):
        extra_path = folder / extra
        if extra_path.is_file():
            preloaded.append((f"runs/{change_id}/{extra}", extra_path))

    for label, path in preloaded:
        content = _read_if_exists(path)
        if content is not None:
            sections.append(f"### File: `{label}`\n```markdown\n{content.strip()}\n```")
    return "\n\n".join(sections)


def _extract_plan_files(plan_text: str) -> set[str] | None:
    """Extract approved POSIX file paths from 03-implementation-plan.md JSON block."""
    parsed = extract_json_block(plan_text)
    if not parsed:
        return None
    paths: set[str] = set()
    for task in parsed.get("tasks", []):
        if isinstance(task, dict):
            for fpath in task.get("files", []):
                if isinstance(fpath, str) and fpath.strip().endswith(".py"):
                    paths.add(fpath.strip().lstrip("./").replace("\\", "/"))
    for section in ("tests_to_add_or_change", "existing_tests_in_conflict"):
        for item in parsed.get(section, []):
            if not isinstance(item, dict):
                continue
            raw = str(item.get("test", ""))
            for token in re.findall(r"(?:campusflow|tests)/[A-Za-z0-9_./-]+\.py", raw):
                paths.add(token.lstrip("./"))
    return paths or None


def _build_coder_prompt(
    change_id: str,
    repo_root: Path,
    *,
    last_verification_artifact: str | None = None,
) -> str:
    folder = run_dir(change_id, repo_root)
    sections = [
        f"Implement the human-approved plan for `{change_id}`.",
        "Use `read_repo_file`, `search_repo`, `write_coder_file`, and `run_verification`. "
        "Modify ONLY files authorized by the approved plan.",
    ]
    preloaded = [
        (f"runs/{change_id}/00-change-request.md", folder / "00-change-request.md"),
        (f"runs/{change_id}/03-implementation-plan.md", folder / "03-implementation-plan.md"),
        (f"runs/{change_id}/04-human-plan-approval.md", folder / "04-human-plan-approval.md"),
        ("docs/ARCHITECTURE.md", repo_root / "docs/ARCHITECTURE.md"),
    ]
    if last_verification_artifact:
        preloaded.append(
            (f"runs/{change_id}/{last_verification_artifact}", folder / last_verification_artifact)
        )

    for label, path in preloaded:
        content = _read_if_exists(path)
        if content is not None:
            sections.append(f"### File: `{label}`\n```markdown\n{content.strip()}\n```")
    return "\n\n".join(sections)


def _build_test_analyst_prompt(change_id: str, repo_root: Path) -> str:
    folder = run_dir(change_id, repo_root)
    sections = [
        f"Analyze test coverage and gaps for `{change_id}`.",
        "Use `git_diff_readonly`, `read_repo_file`, and `write_test_file` (ONLY under `tests/`). "
        "Do NOT modify application code and do NOT declare Verification PASS.",
    ]
    preloaded = [
        (f"runs/{change_id}/00-change-request.md", folder / "00-change-request.md"),
        ("docs/REQUIREMENTS.md", repo_root / "docs/REQUIREMENTS.md"),
        (f"runs/{change_id}/03-implementation-plan.md", folder / "03-implementation-plan.md"),
        (f"runs/{change_id}/05-coder-report.md", folder / "05-coder-report.md"),
    ]
    for label, path in preloaded:
        content = _read_if_exists(path)
        if content is not None:
            sections.append(f"### File: `{label}`\n```markdown\n{content.strip()}\n```")
    return "\n\n".join(sections)


def default_verification_runner(
    change_id: str,
    repo_root: Path,
    iteration: int,
) -> tuple[bool, str, str]:
    """Run deterministic Verification Gate (`scripts/verify_repo.py`) and save evidence."""
    script = repo_root / "scripts" / "verify_repo.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = f"# Verification {change_id} (iteration {iteration}) — {utc_now()}\n\n"
    output += proc.stdout + proc.stderr
    artifact_name = (
        "07-verification.txt" if iteration == 1 else f"07-verification.iter{iteration}.txt"
    )
    out_path = run_dir(change_id, repo_root) / artifact_name
    out_path.write_text(output, encoding="utf-8")
    return proc.returncode == 0, output, artifact_name


def adk_agent_runner(
    agent: Any,
    prompt_text: str,
    session_id: str,
    initial_state: dict[str, Any] | None = None,
) -> str:
    """Run a single ADK agent in an isolated InMemorySessionService session."""
    from dotenv import load_dotenv
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    load_dotenv()

    async def _execute() -> str:
        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            app_name="factory_app",
            session_service=session_service,
        )
        await session_service.create_session(
            app_name="factory_app",
            user_id="factory_orchestrator",
            session_id=session_id,
            state=initial_state or {},
        )
        message = types.Content(role="user", parts=[types.Part(text=prompt_text)])
        final_text = ""
        async for event in runner.run_async(
            user_id="factory_orchestrator",
            session_id=session_id,
            new_message=message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(
                    part.text for part in event.content.parts if getattr(part, "text", None)
                )
        return final_text

    return asyncio.run(_execute())


def default_security_runner(repo_root: Path) -> dict[str, Any]:
    """Run deterministic security scanners without LLM involvement."""
    from scripts.security_scan import run_all_scans

    return run_all_scans(repo_root)


def _build_reviewer_prompt(
    change_id: str,
    repo_root: Path,
    *,
    verification_artifact: str | None = None,
) -> str:
    """Build strictly independent Reviewer context (NEVER includes coder-report.md)."""
    folder = run_dir(change_id, repo_root)
    sections = [
        f"Perform an independent read-only code review for `{change_id}`.",
        "Use `git_diff_readonly`, `read_repo_file`, and `search_repo` to inspect real code and "
        "tests. Verify all APIs/dependencies exist. Never trust unverified claims.",
    ]
    preloaded = [
        (f"runs/{change_id}/00-change-request.md", folder / "00-change-request.md"),
        ("docs/REQUIREMENTS.md", repo_root / "docs/REQUIREMENTS.md"),
        ("docs/SPEC.md", repo_root / "docs/SPEC.md"),
        ("docs/ARCHITECTURE.md", repo_root / "docs/ARCHITECTURE.md"),
    ]
    verif_name = verification_artifact or "07-verification.txt"
    preloaded.append((f"runs/{change_id}/{verif_name}", folder / verif_name))

    for label, path in preloaded:
        content = _read_if_exists(path)
        if content is not None:
            sections.append(f"### File: `{label}`\n```markdown\n{content.strip()}\n```")
    return "\n\n".join(sections)


def _build_security_prompt(
    change_id: str,
    repo_root: Path,
    scanner_report: dict[str, Any],
) -> str:
    """Build strictly independent Security context grounded in deterministic scanner results."""
    folder = run_dir(change_id, repo_root)
    sections = [
        f"Perform an independent read-only security review for `{change_id}`.",
        "Base your assessment FIRST on the deterministic scanner output below, then inspect "
        "changed code with `git_diff_readonly` and `read_repo_file` for authz/IDOR, injection, "
        "data exposure, and prompt injection.",
    ]
    preloaded = [
        (f"runs/{change_id}/00-change-request.md", folder / "00-change-request.md"),
        ("docs/REQUIREMENTS.md", repo_root / "docs/REQUIREMENTS.md"),
    ]
    for label, path in preloaded:
        content = _read_if_exists(path)
        if content is not None:
            sections.append(f"### File: `{label}`\n```markdown\n{content.strip()}\n```")
    sections.append(
        "### Deterministic Security Scanner Output\n```json\n"
        f"{json.dumps(scanner_report, indent=2)}\n```"
    )
    return "\n\n".join(sections)


class FactoryOrchestrator:
    """Runs Change Requests through the deterministic state machine with Human Gates."""

    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        agent_runner: AgentRunner | None = None,
        verification_runner: VerificationRunner | None = None,
        security_runner: SecurityRunner | None = None,
        max_retries: int = 3,
        max_verify_iterations: int = 3,
        base_backoff_seconds: float = 2.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        model_override: str | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.agent_runner = agent_runner or adk_agent_runner
        self.verification_runner = verification_runner or default_verification_runner
        self.security_runner = security_runner or default_security_runner
        self.max_retries = max_retries
        self.max_verify_iterations = max_verify_iterations
        self.base_backoff_seconds = base_backoff_seconds
        self.sleep_fn = sleep_fn
        self.model_override = model_override

    def _invoke_with_retry(
        self,
        state: dict[str, Any],
        agent: Any,
        prompt_text: str,
        initial_state: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        session_id = f"{state['change_id']}-{agent.name}-{uuid.uuid4().hex[:8]}"
        original_model = getattr(agent, "model", None)
        if self.model_override is not None:
            agent.model = self.model_override

        try:
            for attempt in range(self.max_retries + 1):
                try:
                    output = self.agent_runner(agent, prompt_text, session_id, initial_state)
                    return output, session_id
                except Exception as exc:
                    if not _is_transient_error(exc) or attempt >= self.max_retries:
                        save_state(state, self.repo_root)
                        raise
                    state["rate_limit_retries"] = state.get("rate_limit_retries", 0) + 1
                    save_state(state, self.repo_root)
                    delay = self.base_backoff_seconds * (2**attempt)
                    self.sleep_fn(delay)
        finally:
            if self.model_override is not None and original_model is not None:
                agent.model = original_model

        raise RuntimeError("Unreachable retry state")

    def _run_intake(self, state: dict[str, Any]) -> dict[str, Any]:
        cid = state["change_id"]
        if state["status"] != INTAKE_RUNNING:
            transition(
                state,
                INTAKE_RUNNING,
                actor="Orchestrator",
                note="Starting IntakeAgent",
                repo_root=self.repo_root,
            )

        prompt = _build_intake_prompt(cid, self.repo_root)
        output, session_id = self._invoke_with_retry(state, agents.intake_agent, prompt)

        artifact_name = "01-intake-report.md"
        (run_dir(cid, self.repo_root) / artifact_name).write_text(output, encoding="utf-8")

        parsed = extract_json_block(output) or {}
        recommendation = str(parsed.get("recommendation", "")).strip().upper()

        if recommendation == "PROCEED":
            return transition(
                state,
                PLANNING_RUNNING,
                actor="IntakeAgent",
                session_id=session_id,
                artifact=artifact_name,
                note="Intake recommendation: PROCEED",
                repo_root=self.repo_root,
            )

        # Fail-safe: any ambiguity or missing recommendation blocks at Gate 0.
        state["human_gates"]["clarification"] = "PENDING"
        return transition(
            state,
            AWAITING_CLARIFICATION,
            actor="IntakeAgent",
            session_id=session_id,
            artifact=artifact_name,
            note=f"Stopped for Product Owner clarification ({recommendation or 'UNSPECIFIED'})",
            repo_root=self.repo_root,
        )

    def _run_planner(self, state: dict[str, Any]) -> dict[str, Any]:
        cid = state["change_id"]
        if state["status"] != PLANNING_RUNNING:
            transition(
                state,
                PLANNING_RUNNING,
                actor="Orchestrator",
                note="Starting PlannerAgent",
                repo_root=self.repo_root,
            )

        intake_path = run_dir(cid, self.repo_root) / "01-intake-report.md"
        intake_text = _read_if_exists(intake_path) or ""
        prompt = _build_planner_prompt(cid, self.repo_root)
        output, session_id = self._invoke_with_retry(
            state,
            agents.planner_agent,
            prompt,
            initial_state={"intake_report": intake_text},
        )

        artifact_name = "03-implementation-plan.md"
        (run_dir(cid, self.repo_root) / artifact_name).write_text(output, encoding="utf-8")

        parsed = extract_json_block(output) or {}
        if (
            "HUMAN_CLARIFICATION_REQUIRED" in output
            and not parsed.get("tasks")
        ):
            state["human_gates"]["clarification"] = "PENDING"
            return transition(
                state,
                AWAITING_CLARIFICATION,
                actor="PlannerAgent",
                session_id=session_id,
                artifact=artifact_name,
                note="Planner stopped due to unresolved ambiguity",
                repo_root=self.repo_root,
            )

        state["human_gates"]["plan"] = "PENDING"
        return transition(
            state,
            AWAITING_PLAN_APPROVAL,
            actor="PlannerAgent",
            session_id=session_id,
            artifact=artifact_name,
            note="Implementation plan ready; awaiting Human Gate 1 (PO + Tech Lead)",
            repo_root=self.repo_root,
        )

    def _run_coder(self, state: dict[str, Any]) -> dict[str, Any]:
        cid = state["change_id"]
        if state["status"] != CODING_RUNNING:
            transition(
                state,
                CODING_RUNNING,
                actor="Orchestrator",
                note="Starting CoderAgent",
                repo_root=self.repo_root,
            )

        plan_text = _read_if_exists(run_dir(cid, self.repo_root) / "03-implementation-plan.md")
        allowed_paths = _extract_plan_files(plan_text or "")
        last_verif = state.get("verification", {}).get("artifact")
        prompt = _build_coder_prompt(
            cid,
            self.repo_root,
            last_verification_artifact=last_verif if state["iterations"]["verify"] > 0 else None,
        )

        with tools.scoped_coder_paths(allowed_paths):
            output, session_id = self._invoke_with_retry(state, agents.coder_agent, prompt)

        iteration = state["iterations"]["verify"] + 1
        artifact_name = (
            "05-coder-report.md" if iteration == 1 else f"05-coder-report.iter{iteration}.md"
        )
        (run_dir(cid, self.repo_root) / artifact_name).write_text(output, encoding="utf-8")

        return transition(
            state,
            TEST_ANALYSIS_RUNNING,
            actor="CoderAgent",
            session_id=session_id,
            artifact=artifact_name,
            note=f"Implementation pass {iteration} complete",
            repo_root=self.repo_root,
        )

    def _run_test_analyst(self, state: dict[str, Any]) -> dict[str, Any]:
        cid = state["change_id"]
        prompt = _build_test_analyst_prompt(cid, self.repo_root)
        output, session_id = self._invoke_with_retry(state, agents.test_analyst_agent, prompt)

        iteration = state["iterations"]["verify"] + 1
        artifact_name = (
            "06-test-analysis.md" if iteration == 1 else f"06-test-analysis.iter{iteration}.md"
        )
        (run_dir(cid, self.repo_root) / artifact_name).write_text(output, encoding="utf-8")

        return transition(
            state,
            VERIFYING,
            actor="TestAnalystAgent",
            session_id=session_id,
            artifact=artifact_name,
            note=f"Test analysis pass {iteration} complete",
            repo_root=self.repo_root,
        )

    def _run_verification(self, state: dict[str, Any]) -> dict[str, Any]:
        cid = state["change_id"]
        iteration = state["iterations"]["verify"] + 1
        state["iterations"]["verify"] = iteration
        passed, _output, artifact_name = self.verification_runner(cid, self.repo_root, iteration)

        state["verification"] = {
            "status": "PASS" if passed else "FAIL",
            "iteration": iteration,
            "artifact": artifact_name,
        }
        if passed:
            return transition(
                state,
                REVIEWING,
                actor="VerificationGate",
                artifact=artifact_name,
                note=f"Deterministic verification PASS on iteration {iteration}",
                repo_root=self.repo_root,
            )

        if iteration >= self.max_verify_iterations:
            return transition(
                state,
                BLOCKED,
                actor="VerificationGate",
                artifact=artifact_name,
                note=(
                    f"Deterministic verification FAIL after {iteration} iterations "
                    "(max_verify_iterations reached)"
                ),
                repo_root=self.repo_root,
            )

        return transition(
            state,
            CODING_RUNNING,
            actor="VerificationGate",
            artifact=artifact_name,
            note=f"Deterministic verification FAIL on iteration {iteration}; returning to Coder",
            repo_root=self.repo_root,
        )

    def _run_review_and_security(self, state: dict[str, Any]) -> dict[str, Any]:
        cid = state["change_id"]
        verif_artifact = state.get("verification", {}).get("artifact")

        # 1. Independent ReviewerAgent in its own fresh ADK session (no Coder context).
        review_prompt = _build_reviewer_prompt(
            cid, self.repo_root, verification_artifact=verif_artifact
        )
        review_out, review_sid = self._invoke_with_retry(
            state, agents.reviewer_agent, review_prompt
        )
        review_artifact = "08-review-report.md"
        (run_dir(cid, self.repo_root) / review_artifact).write_text(review_out, encoding="utf-8")

        review_json = extract_json_block(review_out) or {}
        review_findings = review_json.get("findings", [])
        must_fix = sum(
            1
            for f in review_findings
            if isinstance(f, dict) and str(f.get("severity", "")).upper() == "MUST_FIX"
        )
        should_fix = sum(
            1
            for f in review_findings
            if isinstance(f, dict) and str(f.get("severity", "")).upper() == "SHOULD_FIX"
        )
        state["review"] = {
            "status": "FAIL" if must_fix > 0 else "PASS",
            "must_fix": must_fix,
            "should_fix": should_fix,
            "session_id": review_sid,
            "artifact": review_artifact,
        }

        # 2. Deterministic security scanners + independent SecurityAgent in a separate session.
        scanner_report = self.security_runner(self.repo_root)
        sec_prompt = _build_security_prompt(cid, self.repo_root, scanner_report)
        sec_out, sec_sid = self._invoke_with_retry(state, agents.security_agent, sec_prompt)
        sec_artifact = "09-security-report.md"
        (run_dir(cid, self.repo_root) / sec_artifact).write_text(sec_out, encoding="utf-8")

        sec_json = extract_json_block(sec_out) or {}
        sec_findings = sec_json.get("findings", [])
        sec_high = max(
            int(scanner_report.get("high", 0)),
            sum(
                1
                for f in sec_findings
                if isinstance(f, dict) and str(f.get("severity", "")).upper() == "HIGH"
            ),
        )
        sec_medium = max(
            int(scanner_report.get("medium", 0)),
            sum(
                1
                for f in sec_findings
                if isinstance(f, dict) and str(f.get("severity", "")).upper() == "MEDIUM"
            ),
        )
        state["security"] = {
            "status": "FAIL" if (sec_high > 0 or not scanner_report.get("ok", True)) else "PASS",
            "high": sec_high,
            "medium": sec_medium,
            "session_id": sec_sid,
            "artifact": sec_artifact,
        }
        state["human_gates"]["findings"] = "PENDING"
        return transition(
            state,
            AWAITING_FINDING_DECISIONS,
            actor="Reviewer+Security",
            session_id=f"{review_sid},{sec_sid}",
            artifact=f"{review_artifact},{sec_artifact}",
            note=(
                f"Independent review complete (must_fix={must_fix}, sec_high={sec_high}); "
                "awaiting Human Gate 2 (Human Reviewer)"
            ),
            repo_root=self.repo_root,
        )

    def run(self, change_id: str) -> dict[str, Any]:
        """Start (or continue from CREATED) a run until the next Human Gate."""
        cid = normalize_change_id(change_id)
        init_run(cid, repo_root=self.repo_root, exist_ok=True)
        return self.resume(cid)

    def resume(self, change_id: str) -> dict[str, Any]:
        """Resume a run from its last checkpoint, enforcing all blocking Human Gates."""
        cid = normalize_change_id(change_id)
        state = load_state(cid, self.repo_root)
        initial_status = state["status"]

        if initial_status in TERMINAL_STATES:
            return state

        if initial_status == AWAITING_CLARIFICATION:
            if state["human_gates"].get("clarification") != "APPROVED":
                raise HumanGateBlockedError(
                    f"{cid} is blocked at Human Gate 0 (AWAITING_CLARIFICATION). "
                    "Product Owner must record a decision with `scripts/approve_gate.py`."
                )
            state = self._run_intake(state)

        if state["status"] in {CREATED, INTAKE_RUNNING}:
            state = self._run_intake(state)

        if state["status"] == PLANNING_RUNNING:
            state = self._run_planner(state)

        if state["status"] == AWAITING_PLAN_APPROVAL:
            plan_decision = state["human_gates"].get("plan")
            if plan_decision == "MODIFIED":
                state = self._run_planner(state)
            elif plan_decision == "APPROVED":
                state = transition(
                    state,
                    CODING_RUNNING,
                    actor="Orchestrator",
                    note="Human Gate 1 APPROVED; starting M2 Coder -> Test Analyst -> Verification",
                    repo_root=self.repo_root,
                )
            elif initial_status == AWAITING_PLAN_APPROVAL:
                raise HumanGateBlockedError(
                    f"{cid} is blocked at Human Gate 1 (AWAITING_PLAN_APPROVAL). "
                    "Product Owner / Tech Lead must approve with `scripts/approve_gate.py`."
                )

        while state["status"] in {CODING_RUNNING, TEST_ANALYSIS_RUNNING, VERIFYING}:
            if state["status"] == CODING_RUNNING:
                state = self._run_coder(state)
            elif state["status"] == TEST_ANALYSIS_RUNNING:
                state = self._run_test_analyst(state)
            elif state["status"] == VERIFYING:
                state = self._run_verification(state)

        if state["status"] == REVIEWING:
            state = self._run_review_and_security(state)

        if (
            state["status"] == AWAITING_FINDING_DECISIONS
            and initial_status == AWAITING_FINDING_DECISIONS
            and state["human_gates"].get("findings") == "PENDING"
        ):
            raise HumanGateBlockedError(
                f"{cid} is blocked at Human Gate 2 (AWAITING_FINDING_DECISIONS). "
                "Human Reviewer must record decisions with `scripts/approve_gate.py`."
            )

        return state
