# ADR-002 — Conservar el layout del starter (`campusflow/`, `factory_app/`)

- Estado: **Aceptado**
- Fecha: 2026-11-16

## Contexto

El documento del proyecto sugiere un layout `product/` + `factory/agents/...`. El starter entregado
usa `campusflow/` + `factory_app/`, y de ese layout dependen `agents-cli-manifest.yaml`,
`pyproject.toml`, los tests de contrato (`tests/factory/test_contracts.py`), la CI y `adk run factory_app`.

## Decisión

Mantener el layout del starter. Los componentes nuevos de la fábrica se agregan dentro de
`factory_app/` (`orchestrator.py`, `state.py`, `gates.py`, `evidence.py`, `contracts/`).
La documentación de la fábrica vive en `docs/factory/` para no mezclarla con los documentos del
producto que los agentes tratan como fuente de verdad.

## Consecuencias

- (+) Cero riesgo de romper tooling del curso; el profesor reconoce la estructura.
- (−) Diferencia de nombres con el layout sugerido; queda justificada aquí y en `docs/REPO_MAP.md`.
