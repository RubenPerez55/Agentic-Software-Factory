# ADR-004 — Corregir el lint del baseline antes del primer run

- Estado: **Aceptado e implementado** (2026-11-16, commit `chore: fix baseline lint`)
- Fecha: 2026-11-16

## Contexto

El starter falla `ruff` con 7 errores de estilo (ver [BASELINE.md](../BASELINE.md)). Como
Verification bloquea con ruff en FAIL, ningún CR podría pasar el gate.

## Opciones

1. Corregir formato (orden de imports, partir líneas largas) en un commit `chore: fix baseline lint`.
2. Relajar la configuración de ruff (`line-length`, ignorar `I001`).
3. Correr ruff solo sobre archivos cambiados.

## Decisión propuesta

Opción 1. Es un cambio sin efecto en comportamiento ni en aserciones de tests, verificable con
`pytest` antes/después. La opción 2 equivale a debilitar un gate; la 3 esconde deuda.

## Consecuencias

- El commit toca `tests/product/test_service.py` solo en imports; se documenta para que no se
  confunda con "modificar tests para pasar".
