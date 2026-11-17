# Máquina de estados de un run

El estado vive en `runs/<CR-ID>/factory-state.json` (fuente de verdad del orquestador) y al
final se consolida en `factory-run.json` (historial completo). El flujo **nunca** depende de la
conversación con el modelo.

## Estados

| Estado | Quién actúa | Sale hacia |
|---|---|---|
| `CREATED` | orquestador | `INTAKE_RUNNING` |
| `INTAKE_RUNNING` | Intake Agent | `AWAITING_CLARIFICATION` · `PLANNING_RUNNING` |
| `AWAITING_CLARIFICATION` | **Product Owner** (Gate 0) | `INTAKE_RUNNING` (con aclaración) · `REJECTED` |
| `PLANNING_RUNNING` | Planner Agent | `AWAITING_PLAN_APPROVAL` · `AWAITING_CLARIFICATION` |
| `AWAITING_PLAN_APPROVAL` | **Product Owner + Tech Lead** (Gate 1) | `CODING_RUNNING` · `PLANNING_RUNNING` (MODIFIED) · `REJECTED` |
| `CODING_RUNNING` | Coder Agent | `TEST_ANALYSIS_RUNNING` |
| `TEST_ANALYSIS_RUNNING` | Test Analyst Agent | `VERIFYING` |
| `VERIFYING` | Gate determinista | `REVIEWING` (PASS) · `CODING_RUNNING` (FAIL, iteración+1) · `BLOCKED` (iteraciones agotadas) |
| `REVIEWING` | Reviewer + Security | `AWAITING_FINDING_DECISIONS` |
| `AWAITING_FINDING_DECISIONS` | **Human Reviewer** (Gate 2) | `FIXING` (hay MUST FIX aceptados/modificados) · `CONSOLIDATING_EVIDENCE` |
| `FIXING` | Coder Agent (solo findings autorizados) | `REVERIFYING` |
| `REVERIFYING` | Gate determinista + scanners | `REREVIEWING` (PASS) · `FIXING` (FAIL) |
| `REREVIEWING` | Reviewer + Security | `AWAITING_FINDING_DECISIONS` |
| `CONSOLIDATING_EVIDENCE` | Evidence Agent / lógica | `AWAITING_RELEASE_DECISION` |
| `AWAITING_RELEASE_DECISION` | **Release Manager** (Gate 3) | `READY_FOR_HUMAN_MERGE` · `NOT_READY` |
| `READY_FOR_HUMAN_MERGE` | terminal (máximo automatizado) | — |
| `NOT_READY` / `REJECTED` / `BLOCKED` | terminal | — |

## Reglas que el orquestador hace cumplir

1. No se entra a `CODING_RUNNING` si `human_gates.plan != APPROVED`.
2. No se entra a `REVIEWING` si la última verificación no es `PASS`.
3. No se entra a `CONSOLIDATING_EVIDENCE` con findings sin decisión humana.
4. No existe transición automática a "merged".
5. Máximo de iteraciones Coder ↔ Verification/Review configurable (propuesta: 3) → `BLOCKED` y escalamiento humano.
6. Cada transición agrega un evento a `history[]` con timestamp, actor (agente o persona+rol) y artefacto producido.

## Borrador de `factory-state.json`

```json
{
  "change_id": "CR-001",
  "status": "AWAITING_PLAN_APPROVAL",
  "branch": "cr/CR-001",
  "iterations": {"verify": 0, "review": 0},
  "human_gates": {
    "clarification": "NOT_REQUIRED",
    "plan": "PENDING",
    "findings": "PENDING",
    "release": "PENDING"
  },
  "verification": {"status": "NOT_RUN"},
  "review": {"status": "NOT_RUN", "must_fix": 0, "should_fix": 0},
  "security": {"status": "NOT_RUN", "high": 0, "medium": 0},
  "history": [
    {"at": "2026-11-17T18:00:00Z", "actor": "IntakeAgent", "session_id": "…",
     "from": "INTAKE_RUNNING", "to": "PLANNING_RUNNING", "artifact": "01-intake-report.md"}
  ]
}
```

El formato final de `factory-run.json` se documenta en [`runs/README.md`](../../runs/README.md).
