# Repository Map

| Path | Purpose |
|---|---|
| `campusflow/domain.py` | Product entities |
| `campusflow/repository.py` | SQLite persistence |
| `campusflow/service.py` | Business rules |
| `campusflow/api.py` | HTTP adapter |
| `factory_app/agent.py` | ADK root agent |
| `factory_app/agents.py` | Specialized agents |
| `factory_app/tools.py` | Bounded tools |
| `factory_app/prompts.py` | Agent contracts (prompt form) |
| `factory_app/contracts/` | Agent contracts (YAML: context, allow/deny, output, stop conditions) |
| `factory_app/workflows.py` | ADK workflow (planning phase) |
| `change_requests/` | Work input |
| `scripts/` | Deterministic run/gate helpers |
| `tests/` | Product, factory and eval tests |
| `runs/` | Generated evidence (versioned) |
| `docs/factory/` | Factory design: architecture, state machine, human roles, plan, ADRs (team documentation, not product requirements) |

Planned (not yet created): `factory_app/orchestrator.py`, `factory_app/state.py`,
`factory_app/gates.py`, `factory_app/evidence.py`, `scripts/factory.py`, `scripts/security_scan.py`.
