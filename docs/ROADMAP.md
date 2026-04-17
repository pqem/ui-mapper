# Roadmap ui-mapper

Plan por fases. Cada fase tiene objetivo claro, entregables medibles y criterio de "hecho" explícito. Antes de pasar a la siguiente, la actual debe estar cerrada.

**Principio rector**: ninguna fase empieza sin que la anterior cumpla su criterio de éxito. Esto previene el *"80% en todo, 100% en nada"*.

Ver también: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Fase 0 — Cleanup (ahora)

**Objetivo**: limpiar deuda antes de crecer.

Entregables:
- [x] Sacar ChromaDB de `pyproject.toml` (ver [ADR-001](adr/001-rag-deferred.md))
- [x] Agregar deps opcionales `tui` y `hardware`
- [x] Documento de arquitectura v2 en `docs/`
- [x] ADRs iniciales creados
- [ ] Actualizar `.gitignore` para excluir `maps/*/map.json` y `maps/*/session.json` (los generados localmente no van a git)
- [ ] Remover `maps/affinity-designer/map.json` vacío del repo

**Criterio de éxito**: repo limpio, sin deps muertas, con rumbo documentado. Un colaborador nuevo entiende el proyecto leyendo solo `README.md` + `docs/ARCHITECTURE.md` en <15 min.

---

## Fase 1 — Foundations (P0)

**Objetivo**: las bases que el resto asume. No se puede construir encima sin esto.

Entregables:
- [ ] Schema UIMap v2 con `provenance` y `confidence` por entry
- [ ] Detección automática de versión de app al mapear
- [ ] Hardware watchdog (`pynvml` + `psutil` fallback) con umbrales YAML — [ADR-004](adr/004-hardware-watchdog.md)
- [ ] Profile de usuario (`~/.ui-mapper/profile.yaml`)
- [ ] Modo seguro por defecto (umbrales conservadores en el primer run)
- [ ] Migración: maps existentes v1 → v2 (script one-off)

**Criterio de éxito**:
- Un mapeo de 2h sin supervisión no daña hardware ni pierde progreso
- Cada entry del map se puede trazar a su origen (source + method + confidence)
- `ui-mapper map <app>` avisa si la versión del programa cambió respecto al map anterior

---

## Fase 2 — Consumer (P0)

**Objetivo**: que el map tenga un usuario final. Sin esto, el proyecto no tiene punto.

Entregables:
- [ ] `ui-mapper serve <app>` levanta MCP server local
- [ ] Tools dinámicas generadas automáticamente desde el map
- [ ] Driver mínimo: ejecuta shortcuts (fácil) y clicks por coordenadas (más difícil)
- [ ] Doc de integración: cómo conectar desde Claude Code / Cursor

**Criterio de éxito**: un LLM externo, vía MCP, puede ejecutar al menos 10 acciones en una app mapeada (aunque sea simple, como Notepad o Paint).

---

## Fase 3 — Visual mapper real (P1)

**Objetivo**: desbloquear apps con UI custom (CAD, design, DAW).

Entregables:
- [ ] Loop completo: screenshot → VLM → hipótesis → click → verificación → actualizar map
- [ ] Manejo robusto de dialogs modales
- [ ] Snapshots de debugging guardados por sesión
- [ ] Integración con watchdog (pausa automática si temp alta)

**Criterio de éxito**: Affinity Designer mapeado automáticamente a ≥60% coverage de menús + ≥40% de dialogs en una sesión.

---

## Fase 4 — Registry dinámico + setup inteligente (P1)

**Objetivo**: que la herramienta se mantenga al día sin tener que hacer releases.

Entregables:
- [ ] `config/models.yaml` con manifest versionado
- [ ] Query live a Ollama library + OpenRouter `/models`
- [ ] Benchmark rápido en hardware real del usuario
- [ ] Setup interactivo (Questionary + Rich) con tabla comparativa visible
- [ ] Modo auto: recomendación basada en profile

**Criterio de éxito**: un usuario con hardware desconocido corre `setup` y obtiene una recomendación de provider + modelo fundamentada en benchmark real, no en tablas estáticas del README.

---

## Fase 5 — Feedback loop (P2)

**Objetivo**: los maps se auto-corrigen con el tiempo.

Entregables:
- [ ] `ui-mapper verify <app>` con batería de shortcuts seguros
- [ ] Degradación automática de confidence en entries fallidos
- [ ] Re-mapeo selectivo (solo entries degradados, no todo)
- [ ] Métricas de éxito por `(app, mapper, provider)` persistidas

**Criterio de éxito**: tras `verify`, el map tiene scores actualizados y puede afirmar *"el 85% del map sigue válido, 15% requiere re-mapeo"*.

---

## Fase 6 — TUI agradable (P2)

**Objetivo**: experiencia amigable sin comprometer el CLI — ver [ADR-003](adr/003-tui-optional.md).

Entregables:
- [ ] TUI Textual para `setup` wizard
- [ ] Dashboard vivo durante mapping (progress, GPU temp, ETA, costo acumulado)
- [ ] Reporte post-mapeo con coverage y distribución de confidence
- [ ] Flags para deshabilitar TUI (scripting, CI)

**Criterio de éxito**: un usuario no técnico completa un setup y un mapeo sin leer docs, solo siguiendo la TUI.

---

## Fase 7 — Community maps (P2)

**Objetivo**: el multiplicador de valor. Un map hecho, 100 usuarios beneficiados.

Entregables:
- [ ] Repo `ui-mapper-maps` con convención `<app>@<version>/map.json`
- [ ] `ui-mapper pull <app>[@version]` descarga
- [ ] `ui-mapper push` publica (con revisión manual al principio)
- [ ] Firma de maps (PGP o similar)

**Criterio de éxito**: un usuario nuevo puede mapear Affinity en 30 segundos (descargando map comunitario) en vez de 4h (generando solo).

---

## Fase 8+ — Exploración (P3)

Candidatos, solo si hay señal real de demanda:

- **RAG sobre maps** — solo si un usuario tiene >20 apps mapeadas ([ADR-001](adr/001-rag-deferred.md))
- **Web dashboard** — solo si TUI no alcanza
- **macOS support** — requiere colaborador con equipo
- **Linux support** (X11 + Wayland) — longer-term
- **Fine-tuning de VLMs** específicos para UI — investigación

---

## Señales de alerta (triggers para pausar y re-planear)

- Si una fase se extiende >2× del estimado → re-diseño, no más esfuerzo
- Si 3 fases se completan pero 0 usuarios reales → problema de distribución, no de código
- Si una decisión de un ADR se viola en código → revisar el ADR, no ignorarlo en silencio
- Si el mantenimiento ocupa más tiempo que las features nuevas → simplificar, podar
