# Documentación de ui-mapper

## Documentos principales

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — visión, principios, capas, componentes y contratos. Leer primero.
- **[ROADMAP.md](ROADMAP.md)** — fases con criterios de éxito medibles. Qué se hace, en qué orden, y cuándo parar.
- **[MCP_INTEGRATION.md](MCP_INTEGRATION.md)** — cómo conectar un LLM (Claude Code, Cursor) al server MCP para controlar apps mapeadas.

## Decisiones arquitectónicas (ADRs)

Las decisiones importantes se documentan como ADRs (Architecture Decision Records). Formato estándar, inmutable una vez aceptado. Cuando una decisión cambia, se crea un ADR nuevo que reemplaza al anterior (no se edita el viejo).

- [000 — Template](adr/000-template.md)
- [001 — RAG diferido hasta demanda real](adr/001-rag-deferred.md)
- [002 — Política de idiomas](adr/002-languages.md)
- [003 — TUI como capa opcional, CLI siempre primero](adr/003-tui-optional.md)
- [004 — Hardware watchdog obligatorio con niveles soft/hard](adr/004-hardware-watchdog.md)

## Cómo contribuir a la documentación

1. **ARCHITECTURE.md** se actualiza cuando cambia la visión o un componente crítico.
2. **ROADMAP.md** se actualiza al cerrar una fase o cuando se detecta un trigger de alerta.
3. **ADRs** no se editan una vez aceptados. Para cambiar una decisión, crear uno nuevo que marque al anterior como `Reemplazado por ADR-XXX`.

## Jerarquía de autoridad

Si hay conflicto entre documentos:

1. ADRs aceptados → máxima autoridad en su dominio
2. ARCHITECTURE.md → visión y principios generales
3. ROADMAP.md → orden de ejecución
4. README.md → onboarding y uso básico
5. CLAUDE.md → instrucciones operacionales para asistentes

Si el código contradice los documentos, **arreglar el código** (o, si la contradicción es intencional, documentar la razón y actualizar los docs).
