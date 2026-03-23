# NYCU GenAI HW01 - LLM Chat Web App

This project is a simple Flask-based chat website that lets you talk to LLMs through an OpenAI-compatible API endpoint (configured to use Groq’s `/openai/v1`).

It includes:
- A browser chat UI (model picker, system prompt, generation parameters, streaming toggle).
- A backend chat endpoint that supports both non-streaming and streaming responses (SSE).
- In-memory per-session conversation history.

## Features

- Server-rendered landing page at `/`
- Model list fetched dynamically from `/models`
- Chat via `POST /chat`
  - Non-streaming mode returns the full assistant message as JSON
  - Streaming mode uses Server-Sent Events (SSE) to emit tokens incrementally
- Clear chat history via `POST /clear`
- Markdown rendering in the chat bubbles (client-side via `marked`)
- “Prompt nodes” sidebar that lets you jump back to previously sent user messages

## Tech Stack

- Backend: `Flask`
- LLM client: `openai` (configured with Groq base URL)
- Frontend: Vanilla JS + CSS (all in `templates/index.html`)
- Markdown: `marked` (loaded from CDN)

## Endpoints

### `GET /`

Serves the main UI (`templates/index.html`).

### `GET /models`

Returns the list of supported model identifiers:

```json
{"models":[...]}
```

The list is defined in `app.py` under `MODELS`.

### `POST /chat`

Body (JSON):

| Field | Type | Description |
|---|---:|---|
| `message` | string | User message (required) |
| `system_prompt` | string | Optional system prompt |
| `model` | string | Model name from `/models` |
| `temperature` | number | Defaults to `0.7` |
| `top_p` | number | Defaults to `0.9` |
| `max_tokens` | number | Defaults to `1024` |
| `api_key` | string | Required Groq API key |
| `stream` | boolean | If `true`, returns SSE token stream |

Validation:
- `message` and `api_key` are required; otherwise the server returns `400`.

Response:
- If `stream=false`: JSON
  ```json
  {"content":"...assistant text..."}
  ```
- If `stream=true`: SSE stream
  - Emits lines like `data: {"token":"..."}` for each token chunk
  - Ends with `data: [DONE]`

### `POST /clear`

Clears the conversation history for the current browser session:
```json
{"status":"cleared"}
```

## How Conversation History Works

- The backend stores history in-memory in a Python dict (`conversation_histories`).
- Each browser session gets a `session_id` (stored in Flask’s session cookie).
- History is truncated to `MAX_MESSAGES = 40` to limit context size.
- History is not persistent: it resets when the server restarts.

## Setup & Run

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the server:
   ```bash
   python app.py
   ```
3. Open in your browser:
   - `http://127.0.0.1:5000/`

## Usage (UI)

1. In the left sidebar, paste your Groq API key (field labeled “Groq API Key”).
2. Choose a model from the “Model” dropdown.
3. (Optional) Edit the “System Prompt”.
4. Adjust `Temperature`, `Top-P`, and `Max Tokens`.
5. Toggle “Streaming” on/off.
6. Type a message and click “Send” (or press `Enter`; use `Shift+Enter` for a newline).
7. “Prompt nodes” on the right allow jumping back to earlier user messages.

## Important Notes / Security

- This app accepts your API key in the browser and forwards it to the backend. That is not safe for production deployments.
- The Flask `secret_key` is hard-coded in `app.py` (`groq-chat-secret-key-change-in-prod`). Update it and move secrets to environment variables if you deploy beyond a homework setting.

## Example `curl` Requests

Non-streaming:
```bash
curl -s -X POST http://127.0.0.1:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message":"Hello!",
    "system_prompt":"You are a helpful assistant.",
    "model":"llama-3.3-70b-versatile",
    "temperature":0.7,
    "top_p":0.9,
    "max_tokens":256,
    "api_key":"YOUR_GROQ_API_KEY",
    "stream":false
  }'
```

Streaming (SSE):
```bash
curl -N -X POST http://127.0.0.1:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message":"Write a haiku about spring.",
    "api_key":"YOUR_GROQ_API_KEY",
    "stream":true
  }'
```

