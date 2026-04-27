# NYCU GenAI HW02 — My very powerful chatbot

A Flask-based chat app that talks to LLMs through Groq's OpenAI-compatible API. Supports streaming, tool use, multimodal input, voice transcription, and more.

## Setup & Run

```bash
pip install -r requirements.txt
python app.py
# Open http://127.0.0.1:5000
```

Your Groq API key is entered in the browser sidebar and sent with each request — nothing is stored server-side.

## Features

- **Streaming & non-streaming** chat (SSE token stream or single JSON response)
- **Tool use** — `search_web` (DuckDuckGo) and `execute_python` (subprocess), enabled for compatible models
- **Auto-routing** — uses `llama-3.1-8b-instant` to pick between fast and capable models per request
- **Multimodal** — attach images (base64-encoded); backend auto-switches to a vision-capable model
- **Voice input** — record audio in the browser, transcribed via `/transcribe`
- **Persistent chat history** — stored in SQLite (`instance/chat_history.db`), capped at 40 messages per session
- **Markdown rendering** — client-side via `marked` (CDN)
- **Prompt nodes** — right sidebar lets you jump back to any previous user message
- **Export** — download chat history as a Markdown file

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves the UI |
| GET | `/models` | Returns `{"models": [...]}` |
| POST | `/chat` | Send a message |
| POST | `/clear` | Delete all messages for the current session |
| POST | `/transcribe` | Transcribe audio; multipart `file` + `api_key` → `{"text":"..."}` |
| GET | `/export` | Download chat history as Markdown |

### `POST /chat`

| Field | Type | Description |
|-------|------|-------------|
| `message` | string | User message **(required)** |
| `api_key` | string | Groq API key **(required)** |
| `system_prompt` | string | Optional system prompt |
| `model` | string | Model name from `/models` |
| `temperature` | number | Default `0.7` |
| `top_p` | number | Default `0.9` |
| `max_tokens` | number | Default `1024` |
| `stream` | boolean | `true` → SSE token stream; `false` → JSON |
| `auto_route` | boolean | Let the backend pick the model |

**Non-streaming response:**
```json
{"content": "...assistant text..."}
```

**Streaming response (SSE):**
```
data: {"token":"..."}
data: {"token":"..."}
data: [DONE]
```

## Tool Use

Tool use is enabled for models whose names contain `llama-3.3`, `llama-3.1`, `mixtral`, or `tool-use`.

- **`search_web`** — queries DuckDuckGo via `duckduckgo-search`
- **`execute_python`** — runs Python code in a subprocess (⚠ no sandboxing — dev only)

In streaming mode, tool calls are accumulated, executed, then a second streaming call returns the final answer.

## Example `curl` Requests

Non-streaming:
```bash
curl -s -X POST http://127.0.0.1:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello!",
    "model": "llama-3.3-70b-versatile",
    "temperature": 0.7,
    "max_tokens": 256,
    "api_key": "YOUR_GROQ_API_KEY",
    "stream": false
  }'
```

Streaming:
```bash
curl -N -X POST http://127.0.0.1:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Write a haiku about spring.",
    "api_key": "YOUR_GROQ_API_KEY",
    "stream": true
  }'
```

## Tech Stack

| Layer | Library |
|-------|---------|
| Backend | Flask, Flask-SQLAlchemy |
| LLM client | `openai` SDK (Groq base URL) |
| Database | SQLite |
| Web search | `duckduckgo-search` |
| Frontend | Vanilla JS + CSS |
| Markdown | `marked` (CDN) |

## Security Notes

- The Flask `secret_key` is hard-coded (`groq-chat-secret-key-change-in-prod`). Change it before any non-local deployment.
- `execute_python` runs arbitrary code in a subprocess with no sandboxing. Do not expose publicly.
- The API key is sent from the browser on every request — do not use in a shared or production environment.
