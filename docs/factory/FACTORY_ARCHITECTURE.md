# Arquitectura de la fábrica

> Borrador para la revisión del 19-nov. Complementa `docs/ARCHITECTURE.md` (producto) sin
> modificarlo. Decisiones justificadas en [`decisions/`](decisions/).

## 1. Vista general

```text
                 change_requests/CR-XXX.md
                            |
                 scripts/factory.py run CR-XXX            (CLI humano)
                            |
        +-------------------v--------------------+
        |   Orchestrator (Python determinista)   |  <- lee/escribe runs/CR-XXX/factory-state.json
        |   factory_app/orchestrator.py          |     y decide la siguiente transición
        +---+-----------+-----------+------------+
            |           |           |
   ADK Runner      Gates humanos   Gates deterministas
   (1 sesión       (JSON firmados  (pytest, ruff, contract,
    por agente)     por rol)        semgrep, pip-audit, secrets)
            |           |           |
            +-----------+-----------+
                        |
                runs/CR-XXX/  (evidencia numerada + factory-run.json)
```

**Idea central:** el LLM nunca decide el flujo. Un orquestador determinista ejecuta cada agente ADK
como un paso aislado, guarda su salida como artefacto, actualiza el estado y se **detiene** en cada
Human Gate. El humano registra su decisión con `scripts/approve_gate.py` y reanuda con
`scripts/factory.py resume CR-XXX`. Ver [ADR-001](decisions/ADR-001-deterministic-orchestrator.md).

## 2. Flujo y Human Gates

```text
CR -> Intake --(ambiguo)--> STOP: HUMAN GATE 0 (Product Owner aclara)  --> Intake
          |
          v
       Planner
          |
   == HUMAN GATE 1 ==  Product Owner (alcance/AC) + Tech Lead (plan)
          |  APPROVED
          v
        Coder  (rama cr/CR-XXX, escritura acotada)
          |
     Test Analyst  (solo tests autorizados)
          |
   Verification Gate  (pytest + ruff + contract)  --FAIL--> Coder Fix (máx. N iteraciones)
          |  PASS
          v
   +-------------+--------------+
   Reviewer (RO)          Security (RO + scanners)     <- sesiones separadas, sin contexto del Coder
   +-------------+--------------+
          |
   == HUMAN GATE 2 ==  Human Reviewer: ACCEPTED / REJECTED / MODIFIED / DEFERRED por finding
          |  hay MUST FIX aceptados?
          |-- sí --> Coder Fix -> Re-verification -> Re-review -> HUMAN GATE 2
          v  no
   Evidence consolidation  (evidence-summary, traceability, factory-run.json)
          |
   == HUMAN GATE 3 ==  Release Manager: READY FOR HUMAN MERGE / NOT READY
          |
   READY FOR HUMAN MERGE   (estado máximo automatizado; el merge lo hace un humano)
```

Estados y transiciones formales: [STATE_MACHINE.md](STATE_MACHINE.md).

## 3. Componentes planeados

| Componente | Archivo | Dueño | Estado |
|---|---|---|---|
| Agentes ADK | `factory_app/agents.py` | B | starter (ajustar) |
| Prompts | `factory_app/prompts.py` | B | starter (ajustar a contratos) |
| Contratos de agentes | `factory_app/contracts/*.yaml` | B | **borrador** |
| Tools acotadas | `factory_app/tools.py` | B (escritura) / C (scanners) | starter (read-only) |
| Estado de la fábrica | `factory_app/state.py` | A | por hacer |
| Orquestador | `factory_app/orchestrator.py` | A | por hacer |
| Gates humanos | `factory_app/gates.py` + `scripts/approve_gate.py` | A | starter (extender con rol/nombre) |
| Verification gate | `scripts/verify_repo.py` | C | starter (extender) |
| Security gate | `scripts/security_scan.py` | C | por hacer |
| Evidencia / trazabilidad | `factory_app/evidence.py` | A | por hacer |
| CLI | `scripts/factory.py` (`run`, `resume`, `status`) | A | por hacer |
| Evals | `tests/eval/` | C | starter (3 casos → 6) |

## 4. Permisos por agente (least privilege)

| Agente | Leer repo (allowlist) | Escribir `campusflow/` | Escribir `tests/` | Ejecutar checks | Scanners | Escribir evidencia | Git |
|---|---|---|---|---|---|---|---|
| Intake | docs, CR, REPO_MAP | – | – | – | – | – (lo hace el orquestador) | – |
| Planner | docs, CR, código, tests | – | – | – | – | – | – |
| Coder | docs, CR, código, tests | ✔ (solo archivos del plan aprobado) | ✔ | – | – | – | rama propia, sin push/merge |
| Test Analyst | docs, CR, código, tests, diff | – | ✔ (solo tests nuevos autorizados) | lectura de resultados | – | – | – |
| Reviewer | docs, CR, código, tests, diff, evidencia | – | – | – | – | – | `diff` read-only |
| Security | docs, CR, código, diff, evidencia | – | – | – | ✔ (semgrep, pip-audit, secrets) | – | `diff` read-only |
| Evidence | `runs/<CR>/` | – | – | – | – | ✔ solo `runs/<CR>/` | – |

Nadie: modificar `docs/REQUIREMENTS.md`, `docs/SPEC.md`, borrar/debilitar tests, hacer merge o push a `main`.
El orquestador (código determinista) es quien persiste artefactos, no el LLM, salvo el Evidence Agent.

## 5. Independencia Coder ≠ Reviewer

- Cada agente se ejecuta en una **sesión ADK nueva** (`InMemorySessionService`, `session_id` distinto).
- El Reviewer y Security reciben solo: CR, requisitos/spec/arquitectura, `git diff`, tests y
  la salida de Verification. **No** reciben `coder-report.md` como prueba ni el historial del Coder.
- Se registra en `factory-run.json` el `session_id` de cada paso para demostrarlo.

## 6. Context engineering

- Las tools solo exponen áreas allowlisted (`docs`, `change_requests`, `campusflow`, `tests`, `runs`).
- Paso 1 de cada agente: `docs/REPO_MAP.md` + CR; después `search`/`read` selectivo.
- Se agregará `search_repo(pattern)` para no leer archivos completos innecesariamente.
- Cada artefacto lista en una sección **"Contexto usado"** los archivos que se leyeron (evidencia para la rúbrica).
- Contenido del repo = datos no confiables (defensa contra prompt injection, eval E06).

## 7. Resiliencia ante cuotas (Free Tier)

- Checkpoint en `factory-state.json` después de cada paso; `resume` continúa desde el último paso completo.
- Retry con backoff exponencial ante `429 RESOURCE_EXHAUSTED` (registrado en `factory-run.json` → `rate_limit_retries`).
- Agentes en secuencia; Reviewer/Security pueden ir en paralelo solo si la cuota lo permite.
- Checks deterministas en lugar de LLM siempre que se pueda.

## 8. Modelo

`gemini-3.8-flash` para todos los agentes (referencia del curso). Opcional (bonus): Flash-Lite para
Evidence con medición de costo/latencia.
