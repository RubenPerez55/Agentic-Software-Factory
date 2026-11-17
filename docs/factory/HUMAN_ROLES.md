# Equipo y roles humanos

## Integrantes

| ID | Nombre | GitHub | Frente técnico |
|---|---|---|---|
| A | Ruben Perez | `RubenPerez55` | Orquestador, estado, gates, evidencia |
| B | _(completar)_ | _(completar)_ | Agentes de construcción (Intake, Planner, Coder, Test Analyst) + contexto |
| C | _(completar)_ | _(completar)_ | Verification, Security, Reviewer, evals, CI |

> La asignación de frentes es una propuesta; ajústenla en la primera reunión y actualicen esta tabla.

## Roles humanos de la fábrica

| Rol | Gate | Decide | Registra |
|---|---|---|---|
| **Product Owner** | Gate 0 (aclaración) y Gate 1 (alcance/AC) | Interpretación del CR y criterios de aceptación; responde ambigüedades (CR-005) | `02-human-requirement-decision.md` |
| **Tech Lead** | Gate 1 (plan) | Aprueba / modifica / rechaza plan, arquitectura, alcance y dependencias | `04-human-plan-approval.md` |
| **Human Reviewer** | Gate 2 (findings) | Cada finding: ACCEPTED / REJECTED / MODIFIED / DEFERRED, con razón | `10-human-review-decisions.md` |
| **Release Manager** | Gate 3 (release) | READY FOR HUMAN MERGE / NOT READY con base en la evidencia consolidada | `15-release-decision.json` |

Reglas:

- Cada decisión registra **nombre, rol, fecha y razón**. Sin razón no se acepta la decisión.
- Quien construyó un frente no debería ser Human Reviewer del código generado en ese mismo CR si se puede evitar.
- El merge a `main` lo hace una persona distinta del Release Manager del CR (doble control).

## Rotación por Change Request

Con 3 personas y 4 roles, cada CR una persona cubre dos roles (PO + Tech Lead se pueden combinar
porque ambos actúan en el Gate 1).

| CR | Product Owner | Tech Lead | Human Reviewer | Release Manager |
|---|---|---|---|---|
| CR-001 Waitlist | A | A | B | C |
| CR-003 Duplicados | B | B | C | A |
| CR-002 Autorización | C | C | A | B |
| CR-005 Prioridad (ambiguo) | A | B | — (se detiene) | — |
| CR-004 CSV (si hay tiempo) | B | C | A | C |
| CR sorpresa (defensa) | se decide el día de la defensa | | | |
