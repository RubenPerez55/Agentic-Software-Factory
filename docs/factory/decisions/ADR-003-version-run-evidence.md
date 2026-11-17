# ADR-003 — Versionar la evidencia de `runs/` en Git

- Estado: **Aceptado**
- Fecha: 2026-11-16

## Contexto

El `.gitignore` del starter ignora `runs/*`. Pero la evidencia de cada run (`runs/<CR>/`) es
precisamente lo que se evalúa (trazabilidad, decisiones humanas, `factory-run.json`) y debe
poder revisarse en GitHub.

## Decisión

- Dejar de ignorar `runs/`. Los runs **finales** se commitean.
- Se ignoran solo temporales: `runs/**/tmp/`, `runs/**/*.log`.
- Los runs de prueba que no se quieran conservar se borran antes del commit o se hacen con un
  ID distinto (`CR-001-dryrun`) y se ignoran con `runs/*-dryrun/`.

## Consecuencias

- (+) Evidencia auditable directamente en el repositorio y en los PRs.
- (−) Hay que cuidar que la evidencia no contenga secretos (lo cubre el secret scan del Security Gate).
