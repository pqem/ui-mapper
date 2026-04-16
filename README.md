# ui-mapper

Automatic UI mapper for desktop applications. Generates structured JSON maps that enable LLMs to control any program.

## What it does

1. **Maps any desktop app's UI** — menus, shortcuts, dialogs, tools
2. **Outputs a JSON map** that an LLM can use to control the program
3. **Uses multiple strategies** — LLM knowledge, config files, UI Automation, visual exploration
4. **Free to run** — Gemini API (multi-key rotation) + Ollama local fallback

## Requirements

- **Python 3.10+**
- **Windows 10/11** (UI Automation and visual mapper are Windows-only for now)
- **One of these VLM providers:**
  - Ollama with a vision model (recommended for overnight mapping, no API limits)
  - Gemini API key(s) (free tier, limited daily quota)

### Hardware for Ollama (local VLM)

| GPU VRAM | Recommended model | Install command |
|----------|-------------------|-----------------|
| 8+ GB | qwen2.5-vl:7b | `ollama pull qwen2.5-vl:7b` |
| 6 GB | gemma3:4b | `ollama pull gemma3:4b` |
| 4 GB | qwen2.5-vl:3b | `ollama pull qwen2.5-vl:3b` |
| No GPU | moondream:1.8b | `ollama pull moondream:1.8b` |

Without a GPU, Ollama runs on CPU (~3-6 tokens/sec). Usable but slow.

## Installation

```bash
git clone https://github.com/pqem/ui-mapper.git
cd ui-mapper

# Option A: Install with everything (recommended)
pip install -e ".[all]"

# Option B: Install only what you need
pip install -e .                  # Core only (JSON maps, CLI)
pip install -e ".[gemini]"        # + Gemini API
pip install -e ".[ollama]"        # + Ollama local
pip install -e ".[visual]"        # + Screenshot-based mapping
pip install -e ".[rag]"           # + ChromaDB vector storage
```

### Install Ollama (for local VLM)

1. Download from https://ollama.com/download
2. Install and start: `ollama serve`
3. Pull a vision model: `ollama pull qwen2.5-vl:7b`

### Configure Gemini API keys (optional)

```bash
cp .env.example .env
```

Edit `.env` and add up to 3 Gemini API keys (from different Google accounts for higher quota):

```
GEMINI_API_KEY_1=your-first-key
GEMINI_API_KEY_2=your-second-key
GEMINI_API_KEY_3=your-third-key
```

Get keys at https://aistudio.google.com/apikey

You can also set a single key via environment variable:
```bash
set GOOGLE_API_KEY=your-key
```

## Usage

### 1. Check setup

```bash
python -m ui_mapper setup
```

This detects your hardware (GPU, RAM), checks available providers, and shows configured apps.

### 2. Map an application

> **IMPORTANT: Before running the mapper, you MUST:**
> 1. Open the target application (e.g. Affinity Designer, AutoCAD)
> 2. Have a document/file open inside the application (not just the start screen)
> 3. Make sure the application window is visible on screen (not minimized)
> 4. Close any open dialogs inside the application — start from the normal editing view
>
> The mapper interacts with the application by taking screenshots and clicking menus.
> If the app is not open or not visible, the mapper will not find anything.

```bash
# Map Affinity Designer (visual exploration)
python -m ui_mapper map affinity-designer

# Map AutoCAD (config files + LLM knowledge)
python -m ui_mapper map autocad

# Start fresh (ignore previous progress)
python -m ui_mapper map affinity-designer --no-resume
```

The mapper runs strategies in order of efficiency:
1. **LLM Knowledge** — asks the VLM what it already knows (~30 seconds)
2. **UIA** — walks Windows UI Automation tree (~5 minutes)
3. **Visual** — screenshots + VLM analysis (~2-6 hours for full depth)

### 3. Check progress

```bash
python -m ui_mapper status
```

### 4. View/export the map

```bash
python -m ui_mapper export affinity-designer
```

Maps are saved to `maps/<app-name>/map.json`.

### Overnight mapping

The visual mapper is designed for unattended operation:

1. Open the target app with a document
2. Run `python -m ui_mapper map <app-name>`
3. Leave it running overnight
4. If it crashes or is interrupted, re-run the same command — it resumes from the last checkpoint

**Tip:** Move your mouse to a screen corner to trigger pyautogui's failsafe and stop the mapper.

## Adding a new application

Create `config/apps/your-app.yaml`:

```yaml
display_name: "Your Application"
process_name: "yourapp"          # Windows process name (check Task Manager)
locale: "en"                     # UI language: "en", "es", etc.
platform: "windows"

# Optional: config files to parse (shortcuts, commands, etc.)
config_files:
  - "%APPDATA%/YourApp/shortcuts.xml"

# Visual mapper settings
visual_enabled: true
screenshot_delay_ms: 500
exploration_depth: "full"        # "quick" (~30min), "standard" (~2h), "full" (~6h)

metadata:
  version: "1.0"
  category: "design"
```

Then run: `python -m ui_mapper map your-app`

## Architecture

```
Provider Chain:    Gemini key1 → key2 → key3 → Ollama local
Mapper Priority:   LLM Knowledge → Config Files → UIA → Visual
Knowledge Tiers:   JSON direct → ChromaDB (optional) → Raw files
```

Each component works independently:
- No GPU? → Gemini API works
- No API keys? → Ollama works
- No internet? → Ollama works offline
- No ChromaDB? → JSON maps still work

## Output format

The generated `map.json` contains:

```json
{
  "app_name": "affinity-designer",
  "app_version": "3.2",
  "locale": "es",
  "menus": {
    "Archivo": {
      "name": "Archivo",
      "items": [
        {"name": "Nuevo...", "shortcut": "Ctrl+N"},
        {"name": "Exportar", "children": [
          {"name": "Exportar...", "shortcut": "Ctrl+Alt+Mayús+W"}
        ]}
      ]
    }
  },
  "shortcuts": [
    {"keys": "Ctrl+S", "action": "Guardar", "category": "Archivo"}
  ],
  "tools": [
    {"name": "Move Tool", "shortcut": "V", "category": "Selection"}
  ],
  "dialogs": {
    "export": {"title": "Exportar", "elements": [...]}
  }
}
```

## License

MIT
