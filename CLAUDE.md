# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Run

```bash
pip install -r requirements.txt
python app.py
# Serves at http://127.0.0.1:5000
```

There is no test suite. `test.py`, `test_stream_tools.py`, and `reproduce_issue.py` are standalone manual scripts that call the Groq API directly and require a valid `GROQ_API_KEY` hardcoded inside them.

## Architecture

This is a single-file Flask app (`app.py`) with one Jinja template (`templates/index.html`).

**Backend (`app.py`)**
- Uses the `openai` SDK pointed at Groq's OpenAI-compatible endpoint (`https://api.groq.com/openai/v1`). The API key is sent by the browser on every request — there is no server-side key.
- Chat history is persisted in SQLite (`instance/chat_history.db`) via Flask-SQLAlchemy. Two models: `ChatSession` (one per Flask session cookie) and `ChatMessage`. History is capped at `MAX_MESSAGES = 40`.
- Two tools are defined: `search_web` (DuckDuckGo via `duckduckgo-search`) and `execute_python` (runs code in a subprocess). Tool use is only activated for models whose names contain `llama-3.3`, `llama-3.1`, `mixtral`, or `tool-use`.
- The `/chat` route handles both streaming (SSE, `data: {"token":"..."}` lines ending with `data: [DONE]`) and non-streaming (JSON `{"content":"..."}`) modes. Tool calls in streaming mode are accumulated across chunks and processed after the stream closes, then a second streaming call returns the final answer.
- Auto-routing (`auto_route: true`) uses `llama-3.1-8b-instant` to pick between `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` for each request.
- Multimodal/vision messages arrive as JSON arrays (content parts); the backend auto-switches to `meta-llama/llama-4-scout-17b-16e-instruct` if the selected model is not vision-capable.

**Frontend (`templates/index.html`)**
- Single-page vanilla JS. Sidebar holds all controls (API key, model picker, system prompt, temperature/top-p/max-tokens sliders, streaming toggle, auto-route toggle).
- Markdown rendered client-side with `marked` (CDN).
- "Prompt nodes" panel on the right tracks each user message and allows jumping back to it in the DOM.
- Image uploads are read with `FileReader`, converted to base64, and sent as OpenAI multimodal content-part arrays.
- Audio recording uses `MediaRecorder`; the blob is POSTed to `/transcribe` and the transcript is inserted into the input box.

## Key API Endpoints

| Method | Path | Notes |
|--------|------|-------|
| GET | `/` | Serves the UI |
| GET | `/models` | Returns `{"models": [...]}` |
| POST | `/chat` | Requires `message` and `api_key`; optional `stream`, `auto_route`, `system_prompt`, `model`, `temperature`, `top_p`, `max_tokens` |
| POST | `/clear` | Deletes all messages for the current session |
| POST | `/transcribe` | Multipart form: `file` + `api_key`; returns `{"text":"..."}` |
| GET | `/export` | Downloads chat history as a Markdown file |

## Notes

- The `secret_key` in `app.py` is hardcoded (`groq-chat-secret-key-change-in-prod`). Do not deploy as-is.
- `execute_python` uses `subprocess` with no sandboxing — explicitly noted in the code as unsafe for production.
- The README describes in-memory history, but the actual implementation uses SQLite. The README is outdated on this point.
