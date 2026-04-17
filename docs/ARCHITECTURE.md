# ui-mapper — Arquitectura v2

Documento guía para la evolución del proyecto. Previene scope creep y orienta decisiones técnicas.

- **Versión**: 2.0 (diseño)
- **Fecha**: 2026-04-17
- **Estado**: propuesta aprobada, pendiente de implementación por fases
- **Roadmap operativo**: [ROADMAP.md](ROADMAP.md)
- **Decisiones históricas**: [adr/](adr/)

---

## 1. Visión

**ui-mapper es una herramienta que aprende a usar cualquier programa de escritorio y expone ese conocimiento a LLMs, de forma que un asistente pueda controlar Affinity Designer, AutoCAD, Blender o cualquier otra app sin que alguien haya codeado integración específica.**

La herramienta se comporta como un **organismo vivo**: mejora a medida que aparecen nuevos modelos (vision, reasoning), nuevos métodos de automatización, y nuevas apps. No queda congelada en las capacidades del mes en que fue creada.

**Usuario objetivo**: persona técnica que quiere dar a su LLM la capacidad de manejar software de escritorio — accesibilidad, automatización creativa, integración de workflows.

---

## 2. Principios rectores

Toda decisión técnica se evalúa contra estos principios. Si algo viola varios, no se hace.

1. **Zero-deps hasta que duela**. Cada dependencia es un costo de mantenimiento y un vector de ruptura. No agregar hasta que la necesidad sea demostrada con datos reales.
2. **CLI es sagrado**. Todo debe funcionar por línea de comandos con flags y stdout parseable. TUIs y dashboards son capas encima, nunca sustitutos.
3. **Data-driven sobre hardcoded**. Listas de modelos, apps soportadas, umbrales de hardware: todo en archivos de configuración versionables, no en código.
4. **Graceful degradation**. Si un componente falla, el sistema continúa con menos calidad, no crashea. Si la GPU se calienta, pausa. Si una API agota cuota, usa fallback. Si un mapper no ve la UI, el siguiente lo intenta.
5. **Provenance y confianza explícitas**. Cada dato en un map sabe de dónde vino y con qué certeza. Sin esto, no hay forma de mejorar automáticamente.
6. **Usable sin internet y sin cuenta paga**. El camino feliz funciona con Ollama local + free tier. Cloud acelera pero no es requisito.
7. **Comunidad como multiplicador**. Un map generado por un usuario beneficia a todos. La arquitectura debe facilitar compartir desde el día uno.

---

## 3. Arquitectura de capas

```
┌─────────────────────────────────────────────────────────┐
│  Consumidores                                           │
│  MCP server · TUI dashboard · Web UI · CLI directo      │
├─────────────────────────────────────────────────────────┤
│  API interna (contratos estables)                       │
│  UIMap · Profile · ModelRegistry · SessionState         │
├─────────────────────────────────────────────────────────┤
│  Orquestación                                           │
│  Orchestrator · ProviderManager · Watchdog · Scheduler  │
├─────────────────────────────────────────────────────────┤
│  Estrategias (mappers — pluggable)                      │
│  LLM-knowledge · UIA · Config-file · Visual · custom    │
├─────────────────────────────────────────────────────────┤
│  Proveedores (pluggable)                                │
│  Gemini · Ollama · OpenRouter · Anthropic · LM Studio   │
├─────────────────────────────────────────────────────────┤
│  Infraestructura                                        │
│  Hardware probe · File IO · Process control · Logs      │
└─────────────────────────────────────────────────────────┘
```

**Regla de oro**: cada capa depende solo de las inferiores. Un mapper no llama a un consumidor. Un provider no sabe de maps. Un consumidor no ejecuta mappers, pide al orquestador.

---

## 4. Componentes críticos (por prioridad)

### 4.1 Hardware watchdog — P0

Protección activa del hardware durante sesiones largas. Ver [ADR-004](adr/004-hardware-watchdog.md).

- Thread paralelo, poll cada 30s
- Métricas: temperatura GPU, VRAM usage, progreso del mapper, duración de sesión
- Niveles: **soft** (pausa + espera enfriamiento) y **hard** (stop + checkpoint)
- Umbrales configurables por YAML (laptop ≠ workstation)
- Log visible al usuario: *"pausado 3× por temperatura, +12min"*
- Detección de stuck: sin avance + GPU idle → probable driver colgado → abort limpio

### 4.2 App versioning + provenance — P0

Los maps se pudren si no sabemos contra qué versión corrieron.

- Extraer versión del exe al mapear (PowerShell `Get-Item ... | Select VersionInfo`), guardar en metadata
- Cada entry del map lleva:
  - `source`: cuál mapper lo generó
  - `method`: qué técnica usó (UIA tree walk, VLM screenshot, etc.)
  - `confidence`: 0.0–1.0
  - `verified_at`: timestamp de última validación
- Al correr contra versión nueva del mismo programa: alertar y ofrecer diff-update en vez de re-mapear todo

### 4.3 MCP server output — P0

**Sin consumidor, el map es un documento muerto.** Éste es el componente que cierra el loop "LLM controla cualquier programa".

- Comando `ui-mapper serve <app>` levanta MCP server local
- Expone tools dinámicas derivadas del map: `app.menu.file.save`, `app.shortcut.export_png`, `app.click_at("Tool_Panel/Brush")`
- Un LLM externo (Claude Code, Cursor, etc.) se conecta, recibe tools, controla la app
- Stateless: el server no ejecuta; delega a un **driver** (capa que maneja la app viva)

### 4.4 Visual mapper real — P1

Hoy es stub. Sin esto, CAD/design apps (el caso de uso principal) quedan afuera.

- Loop: screenshot → VLM analiza → hipótesis de elementos → click → captura cambio → confirma → actualiza map
- Manejo de dialogs modales (screenshot antes/después de cada click)
- Timeout por acción + failsafe de pyautogui (esquina) siempre respetado
- Guardar snapshots de debugging en `sessions/<app>/<timestamp>/` para poder post-mortem

### 4.5 Model registry dinámico — P1

El órgano vital del "organismo vivo". Sin esto, la tool se congela en los modelos del mes de su creación.

- Archivo `config/models.yaml` en el repo, versionado, actualizable sin release
- Al `setup`: consulta Ollama library (API pública) + OpenRouter `/models` + manifest remoto
- Benchmark rápido con el hardware del usuario (no specs teóricas)
- Output: tabla comparativa con VRAM necesario, tokens/s medidos, costo, score de calidad
- Usuario elige, o modo `auto` decide según profile y budget

### 4.6 Feedback loop (verify) — P2

- `ui-mapper verify <app>` ejecuta una batería de shortcuts seguros del map
- Si la acción esperaba "abrir diálogo X" y no pasó nada → baja confidence del entry
- Entries con confidence < umbral se re-mapean
- Corrección manual del usuario (fase futura) sube confidence

### 4.7 Community maps — P2

- Convención `<user>/<app>@<version>/map.json` en repo separado (`ui-mapper-maps`)
- `ui-mapper pull affinity-designer@3.2` descarga map compartido
- `ui-mapper push` publica (con revisión manual en arranque)
- Trust: maps firmados por autor. Ratings y verificación comunitaria cuando haya masa crítica.

### 4.8 RAG (diferido) — P3

No ahora. Re-evaluar cuando un usuario tenga >20 apps mapeadas o el MCP server exponga >500 tools. Ver [ADR-001](adr/001-rag-deferred.md).

---

## 5. Contratos clave

### 5.1 UIMap (schema v2)

```yaml
schema_version: "2.0"
app:
  name: "affinity-designer"
  display_name: "Affinity Designer"
  version: "3.2.1"
  version_detected_at: "2026-04-17T09:30:00Z"
  executable_hash: "sha256:..."
metadata:
  generated_by: "ui-mapper v0.x"
  generated_at: "2026-04-17T09:30:00Z"
  session_id: "..."
  duration_seconds: 1834
  providers_used: ["gemini-2.5-flash", "qwen2.5-vl:7b"]
menus:
  - path: "File > Export..."
    shortcut: "Ctrl+Alt+Shift+S"
    opens_dialog: "export"
    provenance:
      source: "uia-mapper"
      method: "uia-tree-walk"
      confidence: 0.95
      verified_at: "2026-04-17T09:30:00Z"
shortcuts: [...]
dialogs: [...]
tools: [...]
```

### 5.2 Profile de usuario

`~/.ui-mapper/profile.yaml`:

```yaml
preferences:
  budget: "balanced"      # time | cost | quality | balanced
  language: "es"
  preferred_provider: "auto"
hardware_thresholds:
  gpu_temp_soft: 80       # °C → pausa
  gpu_temp_hard: 85       # °C → stop
  vram_soft_percent: 90
  vram_hard_percent: 95
  session_max_hours: 6
providers:
  gemini:
    api_keys: ["env:GEMINI_KEY_1", "env:GEMINI_KEY_2"]
  ollama:
    host: "localhost:11434"
    preferred_model: "auto"
  openrouter:
    api_key: "env:OPENROUTER_API_KEY"
    preferred_model: "auto"
```

### 5.3 Model registry manifest

`config/models.yaml`:

```yaml
schema_version: "1.0"
last_updated: "2026-04-17"
vision_models:
  - id: "qwen2.5-vl:7b"
    provider: "ollama"
    min_vram_gb: 8
    quality_score: 0.85
    ocr_level: 4
    languages: ["en", "es", "zh"]
  - id: "gemini-2.5-flash"
    provider: "gemini"
    cost_per_1k_tokens: 0.0
    rate_limit_day: 250
    quality_score: 0.90
    ocr_level: 4
```

---

## 6. Flujos principales

### 6.1 First-time setup

```
$ ui-mapper setup
→ Detecta hardware (GPU, VRAM, CPU, RAM)
→ Consulta model registry (local + remoto)
→ Benchmark rápido con un modelo small
→ Muestra tabla comparativa (Rich)
→ Usuario elige profile (o modo auto con presets)
→ Escribe ~/.ui-mapper/profile.yaml
```

### 6.2 Mapear una app

```
$ ui-mapper map zwcad
→ Carga config/apps/zwcad.yaml (o wizard interactivo si no existe)
→ Verifica pre-condiciones (app abierta, documento cargado, no hay diálogos modales)
→ Detecta versión del programa
→ Activa watchdog
→ Orchestrator corre mappers en orden definido
→ Cada mapper checkpointa al terminar
→ Output: maps/zwcad/map.json
```

### 6.3 Consumir desde un LLM

```
$ ui-mapper serve affinity-designer
→ Levanta MCP server en localhost
→ LLM se conecta, obtiene N tools dinámicas
→ LLM ejecuta: app.menu.file.export_png()
→ Server valida contra map, ejecuta shortcut/click via driver, devuelve resultado
```

### 6.4 Verificar map existente

```
$ ui-mapper verify affinity-designer
→ Toma N shortcuts random del map con confidence alta
→ Los ejecuta de forma segura (documento sandbox temporal)
→ Si un shortcut falla, baja su confidence
→ Reporta: "92% verified, 3 entries degradados"
```

---

## 7. No-goals (prevención de scope creep)

Cosas que **no** hace ui-mapper, aunque sean tentadoras:

- **No es un RPA**. No graba secuencias de usuario ni ejecuta workflows complejos. Expone capacidades; el LLM decide qué hacer con ellas.
- **No entrena modelos**. Consume LLMs. No fine-tunea.
- **No es cross-OS a la fuerza**. Prioridad Windows. macOS cuando haya colaborador con equipo. Linux eventual.
- **No reemplaza APIs oficiales**. Si un programa tiene API/SDK propia, usar eso siempre será mejor. ui-mapper es para cuando no hay API.
- **No es un GUI builder**. Mapea interfaces, no las diseña.
- **No es un framework de testing**. No es el reemplazo de Playwright/Selenium para apps desktop.

---

## 8. Contacto con otros proyectos

**mcp-affinity-designer**: proyecto hermano, MCP específico para Affinity. ui-mapper es el generalista que eventualmente podría reemplazarlo si el visual mapper funciona bien. Por ahora coexisten — mcp-affinity-designer sirve de campo de pruebas para patrones que luego generalizamos aquí.
