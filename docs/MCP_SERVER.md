# ai-factory MCP server

`ai-factory` ships with an [MCP](https://modelcontextprotocol.io) server that
exposes its library API over stdio. Any MCP-aware client (Claude Code, Claude
Desktop, the MCP Inspector, custom agents) can call ai-factory's tools without
shelling out to the CLI.

## Install

```bash
pip install -e ".[mcp]"
```

This adds the `mcp` SDK and registers the `ai-factory-mcp` console script.

You can also launch the server via Python:

```bash
python -m ai_factory.mcp_server
```

## Register with Claude Code

```bash
claude mcp add ai-factory -- ai-factory-mcp
claude mcp list   # should now show ai-factory
```

## Register with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ai-factory": {
      "command": "ai-factory-mcp",
      "env": {
        "ANTHROPIC_API_KEY": "...",
        "OPENAI_API_KEY": "...",
        "GEMINI_API_KEY": "...",
        "AIFACTORY_PROVIDER": "gemini",
        "AIFACTORY_MODEL": "gemini-2.5-flash"
      }
    }
  }
}
```

## Configuration

The server uses the same precedence chain as the CLI:

1. Defaults
2. `~/.aifactory/config.toml`
3. `./aifactory.toml`
4. Environment variables (`AIFACTORY_*`, provider SDK keys)
5. Tool-call arguments (highest priority)

No new credential surface — set the same env vars / config files you already
use for `ai-factory` invocations.

## Tools

| Tool | Wraps | Purpose |
|------|-------|---------|
| `run_prompt` | `ai_factory.runner.run` | Execute a prompt against a provider. Records to ledger. |
| `list_models` | `ai_factory.runner.list_models` | Enumerate models for a provider. |
| `embed` | `ai_factory.runner.embed` | Generate text embeddings. |
| `append_ledger_event` | `ai_factory.ledger.append_event` | Append a custom event to the ledger. |
| `analyze_ledger` | `ai_factory.ledger_analysis.analyze_ledger` | Summarise ledger contents (runs, success rate, latency, costs). |

### `run_prompt`

Required: `prompt`. Optional: `provider`, `model`, `max_retries`,
`capture_prompt`, `capture_output`, `ledger_enabled`, `ledger_path`,
`ledger_format`, `base_url`.

Returns `{output, success, metrics}`.

### `list_models`

Optional: `provider` (defaults to configured provider).

Returns `{provider, models: [{name, context_window, ...}]}`.

### `embed`

Required: `text`. Optional: `provider`, `model`, `ledger_*`, `include_vector`
(default `true` — set `false` to omit large vectors from the response).

Returns `{success, error, dim, metrics, vector?}`.

### `append_ledger_event`

Required: `event_type`, `data`. Optional: `ledger_path`, `ledger_format`.

Returns `{ledger_path, ledger_format}`.

### `analyze_ledger`

Optional: `ledger_path` (defaults to configured).

Returns the full `LedgerSummary` plus convenience fields
(`success_rate_percent`, `average_latency_ms`, `most_used_model`,
`total_cost_usd_if_available`).

## Smoke testing

```bash
# Inspector GUI
npx @modelcontextprotocol/inspector ai-factory-mcp

# Unit tests
pytest tests/test_mcp_server.py -v
```
