"""Deterministic Python orchestrator for the Agentic Software Factory (ADR-001).

Controls state transitions, runs each ADK agent in an isolated session,
persists checkpoints after each step, retries transient 429/503 API errors,
and enforces blocking Human Gates.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import agents
from .state import (
    AWAITING_CLARIFICATION,
    AWAITING_PLAN_APPROVAL,
    CODING_RUNNING,
    CREATED,
    INTAKE_RUNNING,
    PLANNING_RUNNING,
    REPO_ROOT,
    TERMINAL_STATES,
    init_run,
    load_state,
    normalize_change_id,
    run_dir,
    save_state,
    transition,
)

JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
TRANSIENT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")

AgentRunner = Callable[[Any, str, str, dict[str, Any] | None], str]


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


class FactoryOrchestrator:
    """Runs Change Requests through the deterministic state machine with Human Gates."""

    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        agent_runner: AgentRunner | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        model_override: str | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.agent_runner = agent_runner or adk_agent_runner
        self.max_retries = max_retries
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
                    note="Human Gate 1 APPROVED; Coder unlocked (M2 execution pending)",
                    repo_root=self.repo_root,
                )
            elif initial_status == AWAITING_PLAN_APPROVAL:
                raise HumanGateBlockedError(
                    f"{cid} is blocked at Human Gate 1 (AWAITING_PLAN_APPROVAL). "
                    "Product Owner / Tech Lead must approve with `scripts/approve_gate.py`."
                )

        return state
