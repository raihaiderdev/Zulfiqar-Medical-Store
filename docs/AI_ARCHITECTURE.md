# Offline AI Architecture

## Design Principles

1. **Fully offline**: No cloud API, no internet for core features.
2. **Optional**: App works completely without AI model installed.
3. **Permission-aware**: AI tools respect current user's role/permissions.
4. **No direct SQL**: AI never generates or executes SQL directly.
5. **Validated output**: All model responses are parsed and validated before action.
6. **Audit trail**: AI tool calls logged to `audit_logs`.

## Local Inference Stack

```
CopilotService (app/services/copilot_service.py)
    ↓
LocalLLMClient (app/ai/llm_client.py)
    ↓
llama-cpp-python (llama_cpp)
    ↓
GGUF model file (user-configured path)
```

## Tool Registry

```python
# app/ai/tool_registry.py

TOOLS = {
    "search_inventory": {
        "description": "Search medicines by name, formula, or barcode",
        "permission": "medicine.view",
        "schema": {"query": str},
        "handler": lambda args, session: medicine_service.search_medicines(args["query"])
    },
    # ... etc
}
```

Each tool:
- Has a required permission key
- Has a validated argument schema
- Calls an existing service function
- Never executes raw SQL
- Returns sanitized data (no password hashes, no private keys)

## Chat Interface (Phase 3)

```
app/ui/copilot/
    copilot_panel.py     — QWidget sidebar panel
    copilot_dialog.py    — full-screen dialog version
    message_bubble.py    — chat message rendering
    tool_result_widget.py — structured tool result display
```

## Model Setup

Models are NOT bundled in the EXE. Setup steps:
1. Download a compatible GGUF model (see OFFLINE_AI_SETUP.md)
2. Place it in `%APPDATA%\ZulfiqarMedicalStore\models\` (configurable)
3. Configure path in Settings → AI Settings
4. App detects model on startup and shows status in Copilot panel

## Security Guarantees

- AI cannot call `session_scope()` directly
- AI cannot import SQLAlchemy or execute queries
- AI cannot access `password_hash` fields (filtered out of tool responses)
- AI tool calls validated against schema before execution
- All AI actions visible in audit log
- AI cannot navigate to pages the user lacks permission for
- Model output parsed with strict JSON schema — malformed output uses safe fallback
