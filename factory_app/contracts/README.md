# Contratos de agentes

Cada agente declara: rol/objetivo, contexto de entrada, tools permitidas y denegadas, salida,
condiciones de detención y de escalamiento humano (sección 8 del documento del proyecto).

Estos YAML son la **fuente de verdad** del diseño. `prompts.py` y las listas de tools de
`agents.py` deben coincidir con ellos; se agregará un test (`tests/factory/`) que lo verifique.

| Agente | Archivo | Escribe | Salida |
|---|---|---|---|
| Intake | `intake.yaml` | nada | `01-intake-report.md` |
| Planner | `planner.yaml` | nada | `03-implementation-plan.md` |
| Coder | `coder.yaml` | `campusflow/`, `tests/` (solo archivos del plan) | código + `05-coder-report.md` |
| Test Analyst | `test_analyst.yaml` | `tests/` (solo tests nuevos autorizados) | `06-test-analysis.md` |
| Reviewer | `reviewer.yaml` | nada (read-only) | `08-review-report.md` |
| Security | `security.yaml` | nada (read-only + scanners) | `09-security-report.md` |
| Evidence | `evidence.yaml` | `runs/<CR>/` | `14-evidence-summary.md`, `traceability.md` |

Estado: **borrador** para la revisión del 19-nov.
