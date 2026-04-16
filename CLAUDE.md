# ui-mapper — Instructions for Claude

## What this project does
This is a tool that maps desktop application UIs (menus, shortcuts, dialogs, tools) into structured JSON files. These maps allow LLMs to understand and control desktop programs.

## When the user wants to map a program

### Pre-mapping checklist — ALWAYS verify with the user:

1. **Is the target program installed on this PC?** Ask the user to confirm.
2. **Is the program currently open?** If not, tell the user to open it.
3. **Does the program have a document/file loaded?** Many programs show a start screen or empty state when no document is open. The mapper needs the program in its normal editing view with menus and tools visible. Tell the user to create or open a document first.
4. **Is the program window visible (not minimized)?** The visual mapper takes screenshots of the screen. If the window is minimized or behind other windows, it won't work.
5. **Are all dialogs inside the program closed?** The mapper starts by reading the menu bar. If a dialog is covering the menus, it will fail. Tell the user to close any open dialogs.
6. **Does the program have a config file in `config/apps/`?** If not, create one. The minimum config needs:
   - `display_name`: Human-readable name
   - `process_name`: Windows process name (visible in Task Manager > Details tab)
   - `locale`: UI language ("es", "en", etc.)

### How to find the process name
If the user doesn't know the process name, run:
```powershell
Get-Process | Where-Object { $_.MainWindowTitle -ne '' } | Select-Object ProcessName, MainWindowTitle
```
This lists all programs with visible windows. Match by window title.

### Examples of program states that will FAIL:
- Affinity Designer showing the start/welcome screen (no document open)
- AutoCAD with the "Start" tab active (need a drawing open)
- SketchUp showing the template chooser dialog
- Any program that's minimized to the taskbar
- Any program with a modal dialog open (Save As, Export, Preferences, etc.)

### Examples of program states that will WORK:
- Affinity Designer with a blank or existing document open, in the normal editing view
- AutoCAD with a drawing (.dwg) open, command line visible at the bottom
- SketchUp with a model open in the 3D viewport

## Provider setup

### Gemini API (cloud, free but limited)
The user's GOOGLE_API_KEY env var is already configured. Gemini free tier has strict daily limits (~20-250 requests/day depending on the account). For overnight mapping, Ollama is preferred.

### Ollama (local, no limits)
Requires a GPU with enough VRAM. The user has Ollama installed. Check if a vision model is pulled:
```bash
ollama list
```
If no vision model, recommend based on VRAM:
- 8+ GB: `ollama pull qwen2.5-vl:7b`
- 4-6 GB: `ollama pull qwen2.5-vl:3b`
- No GPU: `ollama pull moondream:1.8b` (slow but works)

## Running the mapper

```bash
cd C:\Users\Pablo\Proyectos\ui-mapper
python -m ui_mapper setup                    # Check everything
python -m ui_mapper map <app-name>           # Start mapping
python -m ui_mapper map <app-name> --no-resume  # Start fresh
python -m ui_mapper status                   # Check progress
python -m ui_mapper export <app-name>        # View generated map
```

## Output
Maps are saved to `maps/<app-name>/map.json`. Session state (for resume) is in `maps/<app-name>/session.json`.

## Important notes
- The visual mapper controls mouse and keyboard. The user should not use the PC while it's running.
- Moving the mouse to a screen corner triggers pyautogui's failsafe and stops the mapper.
- If mapping is interrupted, re-running the same command resumes from the last checkpoint.
- The mapper runs strategies in order: LLM Knowledge (fast) → UIA (medium) → Visual (slow). Each one adds more detail to the map.
