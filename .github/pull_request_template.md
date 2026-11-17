## Qué cambia

<!-- Frente: orquestador / agentes / calidad-seguridad / docs. CR relacionado si aplica. -->

## Checklist

- [ ] `uv run pytest -q` en verde
- [ ] `uv run ruff check campusflow tests factory_app scripts` en verde
- [ ] No modifica `docs/REQUIREMENTS.md` ni `docs/SPEC.md` (o tiene decisión del Product Owner enlazada)
- [ ] No elimina ni debilita tests
- [ ] No incluye secretos (`.env`, API keys)
- [ ] Si es un run de la fábrica: evidencia completa en `runs/<CR>/` y decisión del Release Manager
- [ ] Revisado por otra persona del equipo (el merge es siempre humano)
