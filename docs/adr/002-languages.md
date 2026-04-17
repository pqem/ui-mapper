# ADR-002: Política de idiomas (código, docs, UI)

- **Estado**: Aceptado
- **Fecha**: 2026-04-17
- **Decisores**: Pablo

## Contexto

Sin política explícita, los LLMs que contribuyeron al proyecto introdujeron inconsistencias: una instrucción inicial pedía bilingüismo EN/JA sin que existiera audiencia japonesa real. Los comentarios de código quedaron en inglés, la documentación mezclada. El usuario principal es hispanohablante y busca abrir el proyecto a colaboradores LATAM sin cerrar la puerta internacional.

Sin política clara, la inconsistencia se acumula cada vez que una persona (o LLM) distinta toca el repo.

## Decisión

**Código**: inglés.
- Nombres de variables, funciones, clases, módulos
- Comentarios en código fuente
- Nombres de archivos y directorios
- Commit messages
- Issue titles en GitHub

**Documentación** (`README.md`, `docs/`, `CLAUDE.md`): español primario, con sección en inglés cuando el contenido sea orientado a audiencia global (releases, instalación).

**Mensajes al usuario final** (CLI output, TUI, logs visibles): español por defecto, configurable via `profile.language`. Soportar al menos `es` y `en` desde fase 1 de TUI.

**Errores técnicos y logs de debugging**: inglés. Rationale: son googleables, referenciables en stack traces, y usados por colaboradores internacionales.

**Lo que NO hacemos**:
- Bilingüismo obligatorio en todos los archivos
- Japonés, chino u otros idiomas (incluir sin audiencia real = deuda de mantenimiento)
- Traducir comentarios de código

## Consecuencias

### Positivas
- Abre el proyecto a colaboradores LATAM con fricción mínima
- Mantiene el código estándar internacional (oportunidad de contribuciones globales)
- Reduce deuda de mantenimiento (no hay duplicado en cada archivo)

### Negativas
- Un usuario monolingüe español que solo mira el código tendrá que leer inglés
- Cualquier colaborador con preferencia fuerte por inglés en docs verá el `README.md` en español

### Neutras
- La TUI multi-idioma implica i18n file desde Fase 6 — costo aceptable

## Alternativas consideradas

- **Todo en inglés**: descartada. Fuerza a Pablo y colaboradores LATAM a escribir docs en idioma no nativo, calidad sufre.
- **Todo en español**: descartada. Cierra la puerta a colaboración internacional y queda raro (código español + dep names inglés).
- **Bilingüe EN/ES en cada archivo**: descartada. Duplica trabajo de mantenimiento sin beneficio proporcional.
- **EN/JA como estaba**: descartada. No hay audiencia japonesa real, era un artefacto de herramientas usadas en el proceso.

## Revisar cuando

- Si se suma un colaborador internacional con necesidad de docs en EN → considerar traducción automática del README
- Si la herramienta se distribuye fuera de LATAM (paquete PyPI con tracción) → agregar `README.en.md`
