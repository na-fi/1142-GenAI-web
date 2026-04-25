# GitHub MCP Integration — Design Spec

**Date:** 2026-04-25
**Project:** NYCU GenAI HW01 — LLM Chat Web App

---

## Goal

Connect the GitHub MCP server (`@modelcontextprotocol/server-github`) to the existing Flask/Groq chat app so the LLM can search repositories, read files, list issues, search code, and browse commits via natural language.

---

## Architecture

```
Browser → Flask /chat → Groq (with tools)
                              ↓ tool_call: search_repositories(...)
                        Tool Router
                         ├── existing: search_web / execute_python (handled as before)
                         └── github.*: forwarded → GitHubMCPClient → MCP subprocess
                                                                           ↓
                                                                  GitHub REST API
```

**New component: `GitHubMCPClient`** (added to `app.py`)
- Spawns `npx -y @modelcontextprotocol/server-github` as a stdio subprocess at app startup
- Fetches the MCP tool list once and caches it
- Converts MCP tool schemas to OpenAI function-calling format
- Handles `call_tool(name, args)` via JSON-RPC over subprocess stdin/stdout

**Tool router** (in `/chat`)
- Merges GitHub tools with existing tools before each Groq call
- Dispatches tool calls by name: known GitHub tool names → MCP client, others → existing handlers

**No changes** to streaming logic, history, model picker, multimodal, or frontend.

---

## Data Flow

### Startup
1. `GitHubMCPClient` is initialized at module level
2. Subprocess is spawned; MCP tool list is fetched and cached as `github_tools`

### Per request
1. If model supports tool use AND GitHub token is configured → merge `github_tools` into tool list
2. Groq selects tool(s) to call
3. Tool router dispatches:
   - GitHub tool → `mcp_client.call_tool(name, args)` → subprocess → GitHub API → result string
   - Existing tool → `search_web` / `execute_python` as before
4. Tool result returned to Groq as a tool message
5. Groq generates the final answer

### Error handling
- MCP subprocess unavailable → GitHub tools silently excluded; app continues working
- Tool call fails → error string returned as tool result; Groq handles gracefully

---

## GitHub Tools Exposed

| Tool | Description |
|------|-------------|
| `search_repositories` | Find repos by keyword |
| `get_file_contents` | Read a file from any public or authorized repo |
| `list_issues` | List open/closed issues on a repo |
| `search_code` | Search code across GitHub |
| `list_commits` | List recent commits on a branch |

---

## Files Changed

| File | Change |
|------|--------|
| `app.py` | Add `GitHubMCPClient` class; merge tools in `/chat`; load token from env |
| `requirements.txt` | Add `mcp>=1.0.0` |
| `.env` | Add `GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...` (new file, gitignored) |

---

## Dependencies

- **Python:** `mcp>=1.0.0`
- **System:** Node.js (for `npx`); `@modelcontextprotocol/server-github` auto-downloaded by `npx` on first run
- **GitHub token scopes:** `repo` read (minimum); `repo` write for issue/PR creation tools (optional)

---

## Out of Scope

- Frontend changes (GitHub tools appear transparently)
- Write tools (`create_issue`, `create_pull_request`, `push_files`) — read-only tools are sufficient for the demo
- Caching GitHub API responses
- Multi-user token management
