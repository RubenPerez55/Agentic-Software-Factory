# Factory Run Evidence

Cada run vive en `runs/<CR-ID>/` y **se versiona en Git** (ver
[ADR-003](../docs/factory/decisions/ADR-003-version-run-evidence.md)). Usamos el naming del
documento oficial del proyecto (§17), que reemplaza la propuesta original del starter.

```text
runs/CR-001/
  00-change-request.md                # copia del CR al iniciar el run
  01-intake-report.md                 # Intake Agent
  02-human-requirement-decision.md    # Gate 0/1 — Product Owner (aclaración / AC)
  03-implementation-plan.md           # Planner Agent
  04-human-plan-approval.md           # Gate 1 — Tech Lead
  05-coder-report.md                  # Coder Agent
  06-test-analysis.md                 # Test Analyst Agent
  07-verification.txt                 # pytest + ruff + contract (salida real)
  08-review-report.md                 # Reviewer Agent (read-only)
  09-security-report.md               # Security Agent + scanners
  10-human-review-decisions.md        # Gate 2 — Human Reviewer, decisión por finding
  11-fix-report.md                    # solo si hubo findings aceptados/modificados
  12-re-verification.txt              # solo si hubo fix
  13-re-review.md                     # Reviewer + Security según aplique
  14-evidence-summary.md              # Evidence consolidation
  15-release-decision.json            # Gate 3 — Release Manager
  traceability.md                     # Requirement → Task → Code → Test → Finding → Decisión
  factory-state.json                  # estado vivo del orquestador (checkpoint)
  factory-run.json                    # historial estructurado final
```

Si hay varias iteraciones, se agregan sufijos: `07-verification.iter2.txt`, `13-re-review.iter2.md`.

## `factory-run.json` (borrador de esquema)

Debe permitir reconstruir el run sin leer la conversación con el modelo. Lo genera código
determinista a partir de `factory-state.json` y los artefactos.

```json
{
  "change_id": "CR-001",
  "final_status": "READY_FOR_HUMAN_MERGE",
  "branch": "cr/CR-001",
  "base_commit": "<sha>",
  "head_commit": "<sha>",
  "started_at": "...", "finished_at": "...",
  "model": "gemini-3.8-flash",
  "steps": [
    {"seq": 1, "state": "INTAKE_RUNNING", "actor": "IntakeAgent", "session_id": "...",
     "started_at": "...", "finished_at": "...", "artifact": "01-intake-report.md",
     "context_used": ["docs/REQUIREMENTS.md", "change_requests/CR-001-waitlist.md"],
     "result": "PROCEED", "rate_limit_retries": 0}
  ],
  "human_decisions": [
    {"gate": "plan", "role": "Tech Lead", "by": "<nombre>", "decision": "APPROVED",
     "reason": "...", "at": "...", "artifact": "04-human-plan-approval.md"}
  ],
  "verification": [{"iteration": 1, "pytest": "PASS", "tests": 14, "failed": 0, "ruff": "PASS"}],
  "findings": [
    {"id": "RF-1", "source": "Reviewer", "severity": "MUST_FIX",
     "human_decision": "ACCEPTED", "fixed_in_iteration": 2, "rereview": "RESOLVED"}
  ],
  "security": {"semgrep": "PASS", "pip_audit": "PASS", "secrets": "PASS", "high": 0},
  "metrics": {"coder_review_iterations": 1, "human_interventions": 4,
              "rate_limit_retries": 0, "tests_before": 10, "tests_after": 14}
}
```
