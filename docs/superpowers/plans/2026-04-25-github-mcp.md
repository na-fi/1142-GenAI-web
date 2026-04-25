# GitHub MCP Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the GitHub MCP server to the existing Flask/Groq chat app so the LLM can search repos, read files, list issues, search code, and browse commits.

**Architecture:** Add two async helper functions and a sync wrapper to `app.py` that spawn `npx @modelcontextprotocol/server-github` as a subprocess and communicate with it via the `mcp` Python library. Merge the returned GitHub tools into the existing `TOOLS` list before each Groq call. Route GitHub tool calls in `dispatch_tool` to the MCP subprocess.

**Tech Stack:** `mcp>=1.0.0` (Python), Node.js/npx (system), GitHub Personal Access Token

---

### Task 1: Add dependency and configure token

**Files:**
- Modify: `requirements.txt`
- Create: `.env`
- Modify: `.gitignore` (if it exists; create otherwise)

- [ ] **Step 1: Add `mcp` to requirements**

In `requirements.txt`, append:
```
mcp>=1.0.0
```

- [ ] **Step 2: Install it**

```bash
pip install mcp
```

Expected: installs without error. Confirm with `python -c "import mcp; print(mcp.__version__)"`.

- [ ] **Step 3: Create `.env` with your GitHub token**

Create `/Users/ifan/Desktop/HW/GenAI/HW01/.env`:
```
GROQ_API_KEY=your_groq_key_here
TAVILY_API_KEY=your_tavily_key_here
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
```

Token needs at minimum the `public_repo` read scope (Settings → Developer settings → Personal access tokens).

- [ ] **Step 4: Make sure `.env` is gitignored**

Check if `.gitignore` exists:
```bash
cat .gitignore 2>/dev/null || echo "no .gitignore"
```

If missing or `.env` is not listed, create/append:
```
.env
__pycache__/
*.pyc
instance/
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "add mcp dependency and gitignore .env"
```

---

### Task 2: Add GitHub MCP helpers to `app.py`

**Files:**
- Modify: `app.py` (lines 1–17 for imports/env; after line 123 for helpers; after line 181 for startup init)

- [ ] **Step 1: Add `asyncio` import and GitHub token (lines 1–17)**

At the top of `app.py`, after the existing imports, `asyncio` and the mcp imports need to be added. Replace the current imports block (lines 1–17):

```python
import asyncio
import io
import json
import re
import uuid
import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, Response, render_template, request, session, stream_with_context, send_file
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI, APIError
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tavily import TavilyClient
import yfinance as yf

load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
```

- [ ] **Step 2: Add MCP helper functions after `execute_python` (after line 123)**

Insert after the `execute_python` function, before `TOOLS = [`:

```python
async def _run_github_mcp(action, tool_name=None, tool_args=None):
    params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            if action == "list":
                return (await session.list_tools()).tools
            result = await session.call_tool(tool_name, tool_args or {})
            return result.content[0].text if result.content else ""

def _load_github_tools():
    raw = asyncio.run(_run_github_mcp("list"))
    tools = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or t.name,
                "parameters": t.inputSchema,
            },
        }
        for t in raw
    ]
    names = {t.name for t in raw}
    return tools, names

def call_github_tool(name, args):
    return asyncio.run(_run_github_mcp("call", tool_name=name, tool_args=args))
```

- [ ] **Step 3: Initialize GitHub tools at startup (after `TOOLS = [...]` block, after line 181)**

Insert after the closing `]` of the `TOOLS` list:

```python
GITHUB_TOOLS = []
GITHUB_TOOL_NAMES = set()

if GITHUB_TOKEN:
    try:
        GITHUB_TOOLS, GITHUB_TOOL_NAMES = _load_github_tools()
        print(f"[GitHub MCP] Loaded {len(GITHUB_TOOLS)} tools: {sorted(GITHUB_TOOL_NAMES)}")
    except Exception as e:
        print(f"[GitHub MCP] Init failed: {e}")
```

- [ ] **Step 4: Verify startup loads tools**

```bash
python app.py
```

Expected output includes a line like:
```
[GitHub MCP] Loaded 12 tools: ['create_branch', 'create_issue', ...]
```

If it prints `[GitHub MCP] Init failed: ...`, check that `npx` is in your PATH (`which npx`) and your `GITHUB_PERSONAL_ACCESS_TOKEN` is set in `.env`.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "add GitHub MCP helpers and startup tool loading"
```

---

### Task 3: Wire GitHub tools into routing

**Files:**
- Modify: `app.py` — `dispatch_tool` (line 212), and two `params["tools"]` lines (lines 322–324 and 396–398)

- [ ] **Step 1: Update `dispatch_tool` to handle GitHub tools**

Replace the current `dispatch_tool` function (lines 212–223):

```python
def dispatch_tool(name, args):
    """Run a tool and return (preview_markdown, result_string)."""
    if name == "search_web":
        q = args.get("query", "")
        return f"🔍 **Tool: Searching for:** `{q}`...", search_web(q)
    if name == "get_stock_price":
        t = args.get("ticker", "")
        return f"📈 **Tool: Getting stock price for:** `{t}`...", get_stock_price(t)
    if name == "execute_python":
        c = args.get("code", "")
        return f"💻 **Tool: Executing Python code:**\n```python\n{c}\n```", execute_python(c)
    if name in GITHUB_TOOL_NAMES:
        return f"🐙 **GitHub:** `{name}`...", call_github_tool(name, args)
    return f"*Tool not found: {name}*", "Tool not found"
```

- [ ] **Step 2: Merge GitHub tools into the non-streaming Groq call (line 322–324)**

Find this block (inside `if not use_stream:`):
```python
            if model_supports_tools(model):
                params["tools"] = TOOLS
                params["tool_choice"] = "auto"
```

Change to:
```python
            if model_supports_tools(model):
                params["tools"] = TOOLS + GITHUB_TOOLS
                params["tool_choice"] = "auto"
```

- [ ] **Step 3: Merge GitHub tools into the streaming Groq call (line 396–398)**

Find the same block inside `def generate()`:
```python
            if model_supports_tools(model):
                params["tools"] = TOOLS
                params["tool_choice"] = "auto"
```

Change to:
```python
            if model_supports_tools(model):
                params["tools"] = TOOLS + GITHUB_TOOLS
                params["tool_choice"] = "auto"
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "wire GitHub MCP tools into dispatch and Groq calls"
```

---

### Task 4: Manual verification

- [ ] **Step 1: Start the app**

```bash
python app.py
```

Confirm `[GitHub MCP] Loaded N tools` appears in the terminal.

- [ ] **Step 2: Test in the browser**

Open `http://127.0.0.1:5000`. Select `llama-3.3-70b-versatile` (required for tool use). Try these prompts:

- `Search GitHub for flask chat repositories` → should trigger `search_repositories`
- `Show me the README of the anthropics/anthropic-sdk-python repo` → should trigger `get_file_contents`
- `List open issues on the huggingface/transformers repo` → should trigger `list_issues`

Each should show a `🐙 GitHub: <tool_name>...` preview token in the chat before the final answer.

- [ ] **Step 3: Test non-streaming mode**

Toggle streaming off in the sidebar and repeat one prompt. Confirm it still works.
