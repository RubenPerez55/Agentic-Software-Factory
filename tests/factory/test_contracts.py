import yaml

from factory_app import agents, prompts
from factory_app.contract_checks import (
    CONTRACTS_DIR,
    IMPLEMENTED_TOOLS,
    REQUIRED_CONTRACT_KEYS,
    ROOT,
    check_contracts,
)
from factory_app.contract_checks import allow_names as _allow_names


def test_required_repository_contract_files_exist():
    required = [
        "AGENTS.md",
        "docs/REQUIREMENTS.md",
        "docs/SPEC.md",
        "docs/ARCHITECTURE.md",
        "docs/REPO_MAP.md",
        "factory_app/agent.py",
        "factory_app/agents.py",
        "factory_app/tools.py",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    assert not missing, f"Missing contract files: {missing}"


def test_change_requests_exist():
    assert len(list((ROOT / "change_requests").glob("CR-*.md"))) >= 5


def test_env_is_gitignored():
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_all_agent_yaml_contracts_are_complete():
    expected_agents = {
        "intake",
        "planner",
        "coder",
        "test_analyst",
        "reviewer",
        "security",
        "evidence",
    }
    found = {p.stem for p in CONTRACTS_DIR.glob("*.yaml")}
    assert expected_agents <= found

    for name in expected_agents:
        data = yaml.safe_load((CONTRACTS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
        missing = REQUIRED_CONTRACT_KEYS - set(data.keys())
        assert not missing, f"{name}.yaml missing keys: {missing}"
        assert data["agent"] == name
        assert data["model"] == agents.GEMINI_MODEL


def test_agents_tools_match_yaml_least_privilege():
    agent_map = {
        "intake": agents.intake_agent,
        "planner": agents.planner_agent,
        "coder": agents.coder_agent,
        "test_analyst": agents.test_analyst_agent,
        "reviewer": agents.reviewer_agent,
        "security": agents.security_agent,
        "evidence": agents.evidence_agent,
    }
    for name, adk_agent in agent_map.items():
        contract = yaml.safe_load((CONTRACTS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
        allowed = _allow_names(contract)
        actual_tools = {tool.__name__ for tool in adk_agent.tools}

        # Every implemented tool wired to the agent must be allowed by its contract.
        unexpected = (actual_tools & IMPLEMENTED_TOOLS) - allowed
        assert not unexpected, f"{name} has tools not in contract allow list: {unexpected}"

        # Every implemented tool declared in the contract must be wired to the agent.
        expected_implemented = allowed & IMPLEMENTED_TOOLS
        missing = expected_implemented - actual_tools
        assert not missing, f"{name} missing implemented contract tools: {missing}"

    for readonly_agent in (agents.intake_agent, agents.planner_agent, agents.reviewer_agent):
        names = {tool.__name__ for tool in readonly_agent.tools}
        assert "write_run_evidence" not in names
        assert "run_baseline_verification" not in names


def test_planning_prompts_enforce_contract_fields():
    for field in (
        "requested_outcome",
        "affected_requirements",
        "acceptance_criteria",
        "likely_areas",
        "ambiguities",
        "conflicts",
        "context_used",
        "HUMAN_CLARIFICATION_REQUIRED",
    ):
        assert field in prompts.INTAKE_INSTRUCTION

    for field in (
        "scope",
        "tasks",
        "tests_to_add_or_change",
        "existing_tests_in_conflict",
        "architecture_constraints",
        "security_considerations",
        "verification_commands",
        "assumptions",
        "open_questions",
        "context_used",
        "HUMAN_CLARIFICATION_REQUIRED",
    ):
        assert field in prompts.PLANNER_INSTRUCTION


def test_contract_gate_passes():
    assert check_contracts() == []


def test_m2_prompts_enforce_contract_fields():
    for field in ("tasks_done", "deviations_from_plan", "notes_for_verification", "context_used"):
        assert field in prompts.CODER_INSTRUCTION

    for field in (
        "ac_coverage",
        "gaps",
        "tests_added",
        "tests_that_may_mask_defects",
        "context_used",
    ):
        assert field in prompts.TEST_ANALYST_INSTRUCTION


def test_m3_prompts_enforce_contract_fields():
    for field in ("findings", "MUST_FIX", "apis_verified", "context_used"):
        assert field in prompts.REVIEWER_INSTRUCTION

    for field in ("scanner_results", "findings", "HIGH", "secret_detected", "context_used"):
        assert field in prompts.SECURITY_INSTRUCTION
