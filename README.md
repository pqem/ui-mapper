# ui-mapper

Automatic UI mapper for desktop applications. Generates structured maps that enable LLMs to control any program.

## What it does

1. **Maps any desktop app's UI** — menus, shortcuts, dialogs, tools
2. **Outputs a JSON map** that an LLM can use to control the program
3. **Works with multiple knowledge sources** — LLM knowledge, config files, UIA, visual exploration
4. **Uses free VLM providers** — Gemini API (multi-key rotation) + Ollama local fallback

## Quick Start

```bash
# Install core
pip install -e .

# Install with all providers
pip install -e ".[all]"

# Configure API keys (optional — Ollama works without keys)
cp .env.example .env
# Edit .env with your Gemini API keys

# Check setup
python -m ui_mapper setup

# Map an application
python -m ui_mapper map affinity-designer
python -m ui_mapper map autocad
```

## Architecture

```
Provider Chain:    Gemini key1 → key2 → key3 → Ollama local
Mapper Priority:   LLM Knowledge → Config Files → UIA → Visual
Knowledge Tiers:   JSON context → ChromaDB (optional) → Raw files
```

Each component works independently. No GPU? Gemini API works. No API keys? Ollama works. No internet? Ollama works offline.

## Adding a new application

Create `config/apps/your-app.yaml`:

```yaml
display_name: "Your App"
process_name: "yourapp"
locale: "en"
platform: "windows"
config_files: []
visual_enabled: true
```

Then run: `python -m ui_mapper map your-app`

## License

MIT
