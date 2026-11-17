# CR-001 — Revisión de preparación (pre-intake humano)

> Revisión humana previa a correr la fábrica. **No** modifica el CR ni los requisitos: solo deja
> claro qué esperamos que la fábrica detecte, para poder evaluar si lo hizo bien.

## Qué pide

Cuando un evento llega a capacidad, la nueva inscripción entra a una lista de espera (WAITLISTED)
en lugar de rechazarse. Al cancelar un participante activo, se promueve al primero en espera.

## Requisitos afectados

| Fuente | Elemento | Efecto |
|---|---|---|
| `REQUIREMENTS.md` | AC-03.3 (full → rechazo) | **Cambia intencionalmente** (lo dice el propio documento) |
| `REQUIREMENTS.md` | FR-04 / AC-04.1 (cancelación) | Se extiende: cancelar dispara promoción |
| `REQUIREMENTS.md` | FR-01, FR-02 | No deben regresionar (AC-CR001.5) |
| `REQUIREMENTS.md` | NFR-01, NFR-02 | Reglas en Service; tests automatizados obligatorios |
| `SPEC.md` | Register: full → `CapacityReachedError` | Comportamiento queda obsoleto para CR-001 |
| `tests/product/test_service.py` | `test_registration_rejects_when_event_is_full` | Choca con AC-CR001.2 |

## Puntos que el Intake/Planner deberían señalar (y un humano decidir)

1. **Conflicto con un test existente.** `test_registration_rejects_when_event_is_full` espera
   `CapacityReachedError`. Con waitlist eso deja de ser cierto. Cambiar ese test **no es
   debilitarlo** si se reemplaza por uno que verifique WAITLISTED, pero debe ser una decisión
   explícita del Tech Lead en Gate 1, citada en el plan.
2. **SPEC desactualizada.** `SPEC.md` describe el rechazo por capacidad. La regla del curso es no
   editar SPEC para que el código "cumpla"; la actualización debe ser una decisión del Product
   Owner, separada y justificada por el CR, no un efecto del Coder.
3. **Detalles no especificados** (posible ambigüedad menor):
   - ¿Cómo se expone el estado? (`status` en `Registration`: ACTIVE / WAITLISTED)
   - ¿Un usuario en espera puede cancelar su lugar en la lista? (el CR no lo dice)
   - ¿La capacidad cuenta solo ACTIVE? (implícito sí)
   - ¿Qué pasa con duplicados en la lista? (CR-003 es otro CR; no mezclar alcance)
   La fábrica debe listarlos como supuestos/preguntas abiertas y el PO responderlos en Gate 1, no inventarlos.
4. **Persistencia.** Se necesita guardar estado y orden FIFO (columna `status` + orden por `id`
   o timestamp) en `SQLiteCampusFlowRepository`, sin lógica de negocio en el repositorio.

## Criterios de "listo para procesar"

- [x] CR leído y AC identificados (AC-CR001.1 … AC-CR001.5)
- [x] Requisitos y tests afectados identificados
- [x] Riesgos de alcance identificados (no tocar duplicados ni autorización)
- [ ] Roles asignados para este run (ver [HUMAN_ROLES.md](HUMAN_ROLES.md))
- [ ] Baseline en verde (ruff) — ver [BASELINE.md](BASELINE.md)

## Resultado esperado del run

`runs/CR-001/` llega hasta `AWAITING_PLAN_APPROVAL` en la demo del jueves, con
`01-intake-report.md` y `03-implementation-plan.md` que citen los puntos anteriores.
