# Baseline del starter

Ejecutado el 16-nov-2026 sobre el commit `chore: import CampusFlow Agentic Factory starter (unmodified)`.

Entorno: Windows 11, `uv 0.13.3`, Python 3.13 (seleccionado por `uv`), `google-adk 2.14.1`.

```bash
uv sync
uv run pytest -q
uv run ruff check campusflow tests factory_app scripts
```

## Resultado

| Check | Resultado | Notas |
|---|---|---|
| `pytest` | **PASS** — 10 passed, 1 xfailed | El xfail es `test_duplicate_registration_is_rejected` (defecto conocido; lo corrige CR-003) |
| `ruff` | **FAIL** — 7 errores | Solo estilo: 3× `I001` (orden de imports) y 4× `E501` (línea > 100) |

Errores de ruff:

```text
campusflow/api.py:1:1: I001 Import block is un-sorted or un-formatted
campusflow/api.py:4:101: E501 Line too long (104 > 100)
campusflow/repository.py:86:101: E501 Line too long (101 > 100)
campusflow/service.py:1:1: I001 Import block is un-sorted or un-formatted
campusflow/service.py:1:101: E501 Line too long (106 > 100)
tests/product/test_service.py:1:1: I001 Import block is un-sorted or un-formatted
tests/product/test_service.py:3:101: E501 Line too long (116 > 100)
```

## Implicación

El Verification Gate bloquea con ruff en FAIL, así que la fábrica no podría pasar ningún CR desde
este baseline. Decisión en [ADR-004](decisions/ADR-004-baseline-lint.md) (tarea T00).

## Corrección (16-nov-2026)

Commit `chore: fix baseline lint`: `ruff check --fix` reordenó y partió los imports (corrige los
3× `I001` y 3 de los `E501`) y se partió a mano una línea en `repository.py`. Sin cambios de
comportamiento ni de aserciones; en `tests/product/test_service.py` solo cambió el bloque de import.

| Check | Antes | Después |
|---|---|---|
| `pytest` | 10 passed, 1 xfailed | 10 passed, 1 xfailed |
| `ruff` | FAIL (7) | **PASS** |
| `scripts/verify_repo.py` | FAIL | **PASS** |
