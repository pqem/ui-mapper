# Integración MCP — conectar ui-mapper a un LLM

Este documento explica cómo exponer un mapa generado por ui-mapper a un
cliente LLM via [Model Context Protocol](https://modelcontextprotocol.io/)
para que el modelo pueda controlar la aplicación mapeada.

## Requisitos

- Haber mapeado al menos una app: `python -m ui_mapper map <app>` genera
  `maps/<app>/map.json`.
- Instalar el extra `mcp`:
  ```
  pip install -e ".[mcp]"
  ```

## Comando

```bash
# Corre el server en stdio bloqueante (así se conectan los clientes MCP)
python -m ui_mapper serve <app-name>

# Modo prueba — loggea las acciones sin tocar teclado/mouse
python -m ui_mapper serve <app-name> --dry-run
```

La app objetivo **debe estar en foco en pantalla** para que las acciones
lleguen al programa correcto. La ventana minimizada o tapada por otra app
no recibe las pulsaciones.

## Herramientas expuestas

El server expone **11 tools** al cliente MCP. El LLM normalmente combina
una query con una acción.

### Tools de exploración (leer el mapa)

| Tool | Descripción |
|---|---|
| `get_app_info` | Nombre, versión, cobertura del mapa. |
| `list_menus(limit, contains)` | Lista entradas de menú. |
| `list_shortcuts(limit, category, contains)` | Atajos de teclado. |
| `list_tools_registered(limit, category, contains)` | Herramientas de la toolbox. |
| `list_dialogs(limit, contains)` | Diálogos conocidos. |
| `search_map(query, limit)` | Búsqueda full-text a través de todo. |

### Tools de acción (controlar el programa)

| Tool | Descripción |
|---|---|
| `execute_shortcut(keys)` | Ejecuta un atajo (ej. `Ctrl+S`). |
| `execute_menu_action(path)` | Ejecuta una entrada de menú (ej. `File > Export...`). |
| `execute_action_by_description(action)` | Busca y ejecuta la mejor coincidencia para un texto libre. |
| `type_text(text)` | Escribe texto en la ventana focusada. |
| `click_at(x, y, button)` | Click en coordenadas absolutas (usar como último recurso). |

### Flujo típico del LLM

1. `search_map(query="export PNG")` → recibe candidatos
2. `execute_menu_action(path="File > Export...")` → se abre el diálogo
3. `type_text(text="output.png")` → llena un campo
4. `execute_shortcut(keys="Enter")` → confirma

## Configuración en Claude Code

Editar `~/.config/claude-code/claude_config.json` (Linux/macOS) o
`%APPDATA%\Claude\claude_config.json` (Windows):

```json
{
  "mcpServers": {
    "ui-mapper-affinity": {
      "command": "python",
      "args": ["-m", "ui_mapper", "serve", "affinity-designer"],
      "cwd": "C:/Users/Pablo/Proyectos/ui-mapper"
    }
  }
}
```

Claude Code levanta el server cuando lo necesita. Una entrada por app
mapeada — cada app = un server distinto (evita colisiones de nombres de
tool).

## Configuración en Cursor

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ui-mapper-affinity": {
      "command": "python",
      "args": ["-m", "ui_mapper", "serve", "affinity-designer"]
    }
  }
}
```

## Debugging

- `python -m ui_mapper serve <app> --dry-run` imprime qué acción se
  ejecutaría sin pulsar nada realmente. Útil para probar el flow del LLM
  sin riesgo de que abra diálogos reales mientras trabajás en otra cosa.
- Para ver qué tools se registraron sin arrancar un cliente:
  ```python
  from pathlib import Path
  from ui_mapper.mcp_server.server import build_server
  srv = build_server(Path("maps/<app>/map.json"), dry_run=True)
  ```

## Failsafe

- **pyautogui failsafe**: mover el mouse a una esquina de la pantalla
  aborta cualquier acción en curso. No lo desactives.
- **Dry-run en primer run**: cuando conectás por primera vez un cliente
  nuevo al server, corré con `--dry-run` unos minutos para confirmar que
  el LLM no hace algo inesperado.

## Limitaciones actuales (MVP Phase 2)

- `execute_menu_action` usa el shortcut del entry. Si el menu entry no
  tiene shortcut asociado, retorna error. La navegación visual del menú
  (click sobre el menu bar) llegará cuando el visual mapper sea completo
  (Phase 3).
- No hay foco automático de la ventana. El usuario debe traer la app al
  frente antes de pedirle al LLM que actúe.
- No hay validación semántica: si el map tiene un shortcut incorrecto,
  el server lo ejecuta igual. El loop de `verify` (Phase 5) corrige esto.

## Próximos pasos

Ver [ROADMAP.md](ROADMAP.md):

- Phase 3: visual mapper completo → más entries con shortcut/menu_path.
- Phase 4: registry dinámico → profile de usuario afina comportamiento.
- Phase 5: `verify` → baja confidence en entries rotos; el MCP server
  puede leer `confidence` y advertir al LLM antes de ejecutar.
