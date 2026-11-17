# ADR-001 — Orquestador determinista en Python con estado en archivo

- Estado: **Propuesto** (validar en la revisión del 19-nov)
- Fecha: 2026-11-16

## Contexto

El starter usa un `SequentialAgent` de ADK (Intake → Planner). Un `SequentialAgent` corre todo de
corrido: no tiene una forma simple y auditable de pausar días esperando a una persona, ni de
reanudar después de un `429` del Free Tier. La rúbrica pide estado explícito, gates que
**bloqueen** y que el flujo no dependa de una conversación.

## Decisión

- Un orquestador en Python (`factory_app/orchestrator.py`) controla las transiciones definidas en
  [STATE_MACHINE.md](../STATE_MACHINE.md).
- Cada agente ADK se ejecuta **individualmente** con `Runner` en una sesión nueva; su salida se
  guarda como artefacto numerado en `runs/<CR>/`.
- El estado se persiste en `runs/<CR>/factory-state.json` después de cada paso (checkpoint).
- Los Human Gates son estados de espera; la decisión se registra con `scripts/approve_gate.py`
  (JSON con nombre, rol, decisión, razón, timestamp) y se continúa con `scripts/factory.py resume`.
- Los agentes ADK del starter (`agents.py`, `prompts.py`, `tools.py`) se reutilizan.
  `workflows.py` se mantiene para `adk web`/evals de la fase de planeación.

## Consecuencias

- (+) Gates reales y verificables; resume natural tras rate limit; evidencia por paso.
- (+) Sesiones separadas → independencia Coder/Reviewer demostrable.
- (−) Menos "ADK puro" para el flujo completo. Se puede revisar si ADK ofrece un mecanismo de
  human-in-the-loop persistente que cumpla lo mismo (p. ej. tool confirmation / long-running tools).
