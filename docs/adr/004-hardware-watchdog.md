# ADR-004: Hardware watchdog obligatorio con niveles soft/hard

- **Estado**: Aceptado
- **Fecha**: 2026-04-17
- **Decisores**: Pablo

## Contexto

El visual mapper corre VLMs (vision-language models) en GPU durante sesiones que pueden durar 2-6 horas. Al 95% de utilización sostenida, existen riesgos reales:

- Temperatura excesiva por falla de fan o ambiente caluroso
- Saturación de VRAM que dispara OOM y mata el proceso (pierde progreso si no hay checkpoint)
- Driver colgado (GPU idle pero proceso bloqueado) — se agota la sesión sin avance
- Sesión indefinida (humano olvida que está corriendo)

Sin protección activa, el usuario puede volver a una PC apagada por térmico, driver crasheado, o progreso perdido.

## Decisión

Implementar watchdog activo con **niveles soft y hard**, configurable por YAML, corriendo como thread paralelo al mapper.

**Métricas monitoreadas** (poll cada 30s):

| Métrica | Herramienta primaria | Fallback |
|---|---|---|
| Temperatura GPU | `pynvml` (NVIDIA) | WMI (`psutil` + lectura OEM) |
| VRAM usage | `pynvml` | nvidia-smi parse |
| Progreso del mapper | timestamp de último checkpoint | — |
| Duración total de sesión | timer interno | — |
| Utilización GPU | `pynvml` | — |

**Niveles**:

- **Soft**: pausa el mapper, espera que el recurso vuelva a rango, reanuda. Loggeado pero no alarmante. Ej: *"pausado 40s por temp 82°C"*.
- **Hard**: stop + checkpoint + exit con código específico. Alarmante. Ej: *"abortado por temp 88°C, re-ejecutar cuando enfríe"*.

**Umbrales default** (conservadores, configurables en `profile.yaml`):

```yaml
hardware_thresholds:
  gpu_temp_soft: 80       # °C → pausa
  gpu_temp_hard: 85       # °C → stop
  vram_soft_percent: 90
  vram_hard_percent: 95
  session_max_hours: 6
  stuck_detection_minutes: 15   # sin progreso + GPU idle → abort
```

**Modo seguro por defecto**: en el primer `setup`, usar umbrales conservadores (temp_soft 75, session_max 2h). El usuario los sube explícitamente cuando confía en la herramienta.

**Graceful degradation**: si `pynvml` no está disponible (AMD, Intel, sin GPU), el watchdog sigue monitoreando solo lo que puede (duración, progreso, RAM) y loggea qué no puede verificar.

## Consecuencias

### Positivas
- Protección activa contra daños hardware
- Progreso preservado ante imprevistos (siempre checkpointa antes de exit)
- Usuario puede dejar sesiones largas sin supervisar con confianza
- Detección de stuck evita agotar cuota de API o tiempo sin avance

### Negativas
- Dependencia opcional `[hardware]` con `pynvml` + `psutil`
- Overhead mínimo (poll cada 30s es despreciable)
- Falsos positivos posibles en ambientes raros (VM con GPU passthrough)

### Neutras
- Requiere permisos de lectura de sensores GPU (raramente es un problema)

## Alternativas consideradas

- **Sin watchdog**: descartada. Riesgo real de daño hardware y pérdida de progreso.
- **Solo timeout de sesión**: descartada. No protege contra térmico.
- **Límites en hardware via driver**: descartada. No siempre disponible, no gratuito para el usuario configurar.
- **Watchdog externo (systemd service, cron)**: descartada. Platform-specific, complica setup, el mapper necesita coordinación fina (pausar y reanudar, no solo matar).

## Revisar cuando

- Si falsos positivos molestan al usuario → afinar umbrales default
- Si aparece soporte para AMD/Intel GPUs → integrar `rocm-smi`, `intel-gpu-tools`
- Si la herramienta se usa en laptops masivamente → considerar umbrales automáticos según chasis detectado
