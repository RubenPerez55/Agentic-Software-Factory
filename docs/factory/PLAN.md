# Plan de trabajo — 2 semanas

> Equipo de 3 personas. Inicio: lunes 16-nov-2026. Revisión de avances: **jueves 19-nov-2026**.
> Cierre objetivo de la fábrica: **domingo 29-nov-2026** (ensayo de defensa el 30-nov).
> Si la fecha de defensa cambia, se recorta la Fase 6 (evals), nunca los Human Gates ni la evidencia.

## Principio rector

La fábrica es el producto. CampusFlow solo es el escenario. Cada hora invertida debe mejorar
una de estas cosas (en orden de peso en la rúbrica): arquitectura/estado, contratos de agentes,
human gates, context engineering, gates deterministas, review/security independiente,
evidencia/trazabilidad, evals.

## Integrantes y frentes de trabajo

Los nombres se completan en [HUMAN_ROLES.md](HUMAN_ROLES.md). Cada persona es **dueña** de un
frente técnico (quién lo construye) y además **rota** roles humanos por CR (quién decide).

| Integrante | Frente técnico (dueño) | Entregables principales |
|---|---|---|
| **A** — Ruben Perez | Orquestador + estado + gates | `factory_app/orchestrator.py`, `state.py`, `gates.py`, CLI `scripts/factory.py`, checkpoint/resume ante 429, `factory-run.json` |
| **B** — Hector Castro | Agentes de construcción + contexto | Intake, Planner, Coder, Test Analyst; prompts; context engineering (REPO_MAP/search); tools de escritura acotadas |
| **C** — Javier Ortiz | Calidad, seguridad y evaluación | Verification gate (pytest/ruff/contract), Semgrep + pip-audit + secret scan, Reviewer y Security agents, evals E01–E06, CI |

Reglas de colaboración:

- `main` siempre verde (pytest + ruff). Cambios grandes en rama `feat/<frente>-<tema>` + PR revisado por otra persona.
- Las decisiones de arquitectura se registran como ADR en [`decisions/`](decisions/).
- Daily de 10 min (mensaje en el chat del equipo): qué hice, qué sigue, qué me bloquea.

## Calendario

### Semana 1 — Diseño + primer vertical slice

| Día | Fecha | Objetivo | Responsable |
|---|---|---|---|
| Lun | 16-nov | Repo creado, starter versionado, estructura y plan (este documento) | Todos |
| Mar | 17-nov | Cada integrante: `uv sync`, baseline tests, API key de AI Studio en `.env`. Revisar contratos de agentes y máquina de estados | Todos |
| ~~Mar~~ Lun | 16-nov | ✅ **T00**: lint del baseline corregido (solo formato); `main` y CI en verde — [ADR-004](decisions/ADR-004-baseline-lint.md) | Hecho |
| Mar | 17-nov | `state.py` + `orchestrator.py` mínimo: corre Intake → Planner y se detiene en `AWAITING_PLAN_APPROVAL` | A |
| Mar–Mié | 17/18-nov | Prompts de Intake/Planner con salida estructurada; Intake detecta ambigüedad (CR-005) | B |
| Mar–Mié | 17/18-nov | ✅ `verify_repo.py` como Verification Gate (tests/lint/contracts, `--change` → `07-verification.txt`) + CI con secret scan (gitleaks) + primer eval case (CR-005 → STOP, `tests/eval/test_dataset.py`) | C |
| Mié | 18-nov | **Ensayo de demo**: `CR-001` hasta Human Gate 1 y `CR-005` detenido en clarificación | Todos |
| **Jue** | **19-nov** | **Revisión en la Facultad** (ver checklist abajo) | Todos |
| Vie–Dom | 20/22-nov | Coder con escritura acotada (rama por CR) + Test Analyst + Verification Gate bloqueante. **Run completo de CR-001 hasta Verification** | A, B, C |

### Semana 2 — Review, seguridad, evidencia y evals

| Día | Fecha | Objetivo | Responsable |
|---|---|---|---|
| Lun–Mar | 23/24-nov | Reviewer + Security en contexto independiente y read-only; Semgrep/pip-audit/secret scan como gate | C |
| Lun–Mar | 23/24-nov | Human Gate 2 (decisiones por finding) + loop Fix → Re-verify → Re-review | A, B |
| Mié | 25-nov | Evidence consolidation: `traceability.md`, `14-evidence-summary.md`, `factory-run.json`, Release Gate | A |
| Mié–Jue | 25/26-nov | Runs completos: **CR-001** (feature), **CR-003** (bug/regresión), **CR-002** (seguridad) y **CR-005** (ambigüedad) | Todos (rotando roles) |
| Vie–Sáb | 27/28-nov | Evals E01–E06 + métricas + comparación baseline vs mejorado (`agents-cli eval compare`) | C (+B) |
| Dom | 29-nov | Congelar: README final, docs, limpieza; CR-004 si hay tiempo | Todos |
| Lun | 30-nov | **Ensayo de defensa** con un CR inventado por el equipo (simula el CR sorpresa) | Todos |

## Checklist para el jueves 19-nov

| # | Requisito del profesor | Dónde se demuestra | Estado |
|---|---|---|---|
| 1 | Equipo de 2–3 personas definido | [HUMAN_ROLES.md](HUMAN_ROLES.md): Ruben Perez (A), Hector Castro (B), Javier Ortiz (C) | ☑ |
| 2 | Starter descargado y funcionando | commit `chore: import CampusFlow...` | ☑ |
| 3 | Baseline tests ejecutados | `uv run pytest -q` + `uv run ruff check ...` (resultado en [BASELINE.md](BASELINE.md)) | ☑ |
| 4 | Google AI Studio / Gemini configurado | `.env` local de cada integrante (nunca commiteado) | ☐ cada quien |
| 5 | Arquitectura inicial revisada | [FACTORY_ARCHITECTURE.md](FACTORY_ARCHITECTURE.md), [STATE_MACHINE.md](STATE_MACHINE.md) | ☑ borrador |
| 6 | Roles humanos definidos | [HUMAN_ROLES.md](HUMAN_ROLES.md) (rotación por CR) | ☑ confirmar en equipo |
| 7 | Agentes y responsabilidades | [`factory_app/contracts/`](../../factory_app/contracts/) | ☑ borrador |
| 8 | Intake → Planner → Human Gate funcionando | `scripts/factory.py run CR-001` se detiene en Gate 1 | ☐ A + B |
| 9 | CR-001 revisado y listo | [CR-001-readiness.md](CR-001-readiness.md) | ☑ borrador |
| 10 | Repo GitHub con trabajo versionado | este repositorio | ☑ |

## Mapeo con la rúbrica (100 pts)

| Criterio | Pts | Cómo lo cubrimos |
|---|---|---|
| Arquitectura de la fábrica | 15 | Orquestador determinista + máquina de estados explícita persistida en `factory-state.json` |
| Agentes y contratos | 15 | 7 contratos YAML (6 obligatorios + Evidence) con context/allow/deny/output/stop |
| Human-in-the-loop | 15 | 3 gates que **bloquean** (el orquestador no avanza sin el JSON de decisión firmado por rol) |
| Context engineering | 10 | Tools `list/search/read` con allowlist; cada agente declara su contexto; nada de repo dump |
| Verification gates | 10 | `verify_repo.py` = pytest + ruff + contract checks; FAIL regresa al Coder |
| Review + Security | 10 | Sesiones ADK separadas, tools read-only; Semgrep + pip-audit + secret scan |
| Traceability + Evidence | 10 | `runs/<CR>/` con naming oficial, `traceability.md`, `factory-run.json` |
| Agent evaluation | 10 | E01–E06 en `tests/eval/` + métricas + compare |
| Defensa CR sorpresa | 5 | Ensayo el 30-nov |

## Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| Rate limit del Free Tier (429) | Checkpoint después de cada paso + retry con backoff exponencial + `resume`; una sola API key por integrante, nunca rotar keys para evadir cuota |
| El Coder escribe fuera de alcance | Tool de escritura con allowlist de rutas (`campusflow/`, `tests/`) y diff revisado por Verification + Reviewer |
| Reviewer "contaminado" por el Coder | Sesión ADK nueva por agente; el Reviewer solo recibe CR, requisitos, diff y evidencia, nunca el razonamiento del Coder |
| Nos quedamos sin tiempo | Prioridad: gates + evidencia > evals > CR-004 > bonus |
| Modelo inventa APIs | Verification ejecuta el código real; Reviewer verifica que las APIs citadas existan (eval E04) |
