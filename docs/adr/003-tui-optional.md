# ADR-003: TUI como capa opcional, CLI siempre primero

- **Estado**: Aceptado
- **Fecha**: 2026-04-17
- **Decisores**: Pablo

## Contexto

La herramienta necesita ser accesible para usuarios no expertos (gráficos, wizards, feedback visual). Simultáneamente, debe permanecer automatizable: scripting, CI, SSH, integración con otros workflows.

Tentación: hacer una UI amigable (TUI o GUI) como experiencia principal. Riesgo: si la lógica vive en la UI, todo lo no-interactivo se rompe o requiere duplicación.

## Decisión

Arquitectura en 3 capas, con responsabilidades claras:

```
Core CLI (sagrado)       ← todo funciona por flags y stdout JSON
    ↓ capa opcional
TUI (Rich / Textual)     ← presentación amigable, wizards, dashboards vivos
    ↓ capa futura opcional
Web dashboard            ← solo visualización, nunca control
```

**Reglas**:
1. **Toda función accesible por CLI con flags**. Si una feature solo existe por TUI, está mal implementada.
2. **Toda salida parseable**. Flag `--json` o `--output json` disponible en todos los comandos de lectura. Pipeline-able con `jq`.
3. **Cero lógica en la UI**. La TUI solo presenta datos que el core ya produce. Renombrar `mapper` no cambia la TUI; cambia el core y la TUI lo consume.
4. **TUI en dependencia opcional** (`pip install ui-mapper[tui]`). Zero overhead si el usuario no la quiere.
5. **Flag `--no-tui` siempre disponible** para desactivar interactividad (útil en scripts, CI, debugging).

**Stack elegido** (cuando llegue la fase 6):
- `rich` — tablas, progress bars, syntax highlighting, logs estilizados
- `textual` — TUI completa con widgets, mouse, layouts (mismos autores de Rich)
- `questionary` — wizards interactivos (prompts con validación)

## Consecuencias

### Positivas
- El usuario avanzado usa solo CLI; pipelinea salidas; integra en CI
- El usuario nuevo tiene experiencia amigable via TUI
- Misma base de código sirve ambos casos
- Si la TUI tiene un bug, el core sigue funcionando

### Negativas
- Costo inicial: diseñar el core pensando en ambas salidas (JSON + human-readable)
- Doble testing: core con fixtures, TUI con screenshots/snapshots

### Neutras
- La decisión de usar Rich/Textual acopla a un stack particular; mitigado porque es capa opcional y desacoplada

## Alternativas consideradas

- **Solo CLI, sin TUI**: descartada. Deja fuera a usuarios no técnicos, contradice el objetivo de usabilidad.
- **GUI nativa (tkinter, PyQt)**: descartada. Pesa, rompe cross-platform, no scriptable, violaría principio "CLI sagrado".
- **Web app como interfaz principal**: descartada. Requiere servidor web siempre corriendo, overkill para herramienta local, curva de complejidad alta.
- **TUI como experiencia principal con CLI como escape hatch**: descartada. Invierte la jerarquía natural; el día que el CLI necesite algo nuevo, habría que construirlo dos veces.

## Revisar cuando

- Si usuarios piden features que solo tienen sentido visualmente (gráficos interactivos, timeline de sesiones) → considerar web dashboard como capa 3
- Si la TUI crece en complejidad al punto que compite con el core por atención → podar
