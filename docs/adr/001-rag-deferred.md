# ADR-001: RAG diferido hasta demanda real

- **Estado**: Aceptado
- **Fecha**: 2026-04-17
- **Decisores**: Pablo

## Contexto

El `pyproject.toml` incluía `chromadb>=0.5` como dependencia opcional `[rag]`, pensada para vectorizar el conocimiento de los maps y acelerar la búsqueda semántica por parte del LLM.

Análisis del estado real:
- Un map completo pesa entre 1 y 5 MB. Cabe sin problema en el context window de cualquier LLM moderno (100K–1M tokens).
- La búsqueda por path estructurado (`app.menu.file.export`) cubre el 95% de los casos de consumo desde MCP.
- ChromaDB implica: servicio embebido con overhead, modelo de embeddings cargado, deps pesadas.
- El ecosistema RAG embebido evolucionó fuerte en 2025: `sqlite-vec`, `lancedb`, `txtai` son alternativas más livianas que no existían cuando se diseñó chromadb como default.
- Ningún usuario tiene hoy >5 apps mapeadas. El problema que RAG resuelve aún no existe en los datos.

## Decisión

1. **Remover `chromadb` de `pyproject.toml`** (ya en `[rag]` opcional y en `[all]`).
2. **No implementar RAG ahora**. Documentar la intención como capability diferida.
3. **Criterios para re-evaluar** (cualquiera gatilla la revisión):
   - Un usuario alcanza >20 apps mapeadas en una instalación
   - El MCP server expone >500 tools simultáneas y hay evidencia de fricción
   - Aparece una query semántica difusa que la búsqueda por path no resuelve en casos reales
4. **Cuando toque implementar**: evaluar opciones frescas (en ese momento) contra datos reales. No asumir que ChromaDB sigue siendo la mejor.

## Consecuencias

### Positivas
- Menos peso de instalación, menos superficie de bugs
- Reconsideración futura con mejores herramientas y datos reales, no con suposiciones del presente
- Filosofía "zero-deps hasta que duela" respetada

### Negativas
- Cuando se necesite RAG habrá que implementarlo desde cero (costo de desarrollo diferido)
- Usuarios que esperaban RAG como feature disponible quedan decepcionados — mitigado: nadie lo usaba

### Neutras
- El schema del map no cambia; cuando toque RAG, se indexa lo que ya existe

## Alternativas consideradas

- **Mantener ChromaDB como opcional**: descartada. Señal ambigua ("¿lo uso o no lo uso?"), deps muertas sin valor actual.
- **Implementar RAG ahora con sqlite-vec**: descartada. Overengineering para un problema que no existe aún. Violaría principio "data-driven sobre hardcoded".
- **Reemplazar por índice invertido simple en memoria**: descartada por prematura. Si hace falta, se agrega en Fase 5+ cuando haya datos.

## Revisar cuando

- Un usuario reporta que la búsqueda de tools en MCP es lenta o ambigua
- El total de tools expuestas por MCP supera 500
- Una app individual genera un map >20 MB
